import AVFoundation
import ExpoModulesCore
import RoomPlan
import UIKit

struct OraRoomPlanFailure: Error {
  let code: String
  let message: String

  static let cancelled = OraRoomPlanFailure(
    code: "ERR_ROOMPLAN_CANCELLED",
    message: "Scansione annullata."
  )
}

public final class OraRoomPlanModule: Module {
  // These properties are accessed only on the main actor. A request ID also
  // invalidates a camera-permission callback after cancel or a JS runtime reload.
  private var pendingPromise: Promise?
  private var requestID: UUID?
  private var activeController: UIViewController?
  private var isSettling = false
  private var activationObserver: NSObjectProtocol?
  private var activationTimeout: DispatchWorkItem?
  private let lifetimeLock = NSLock()
  private var runtimeDestroyed = false

  public func definition() -> ModuleDefinition {
    Name("OraRoomPlan")

    AsyncFunction("getAvailability") { () -> [String: Any] in
      Self.availability()
    }

    AsyncFunction("scan") { (promise: Promise) -> Void in
      Task { @MainActor in
        self.beginScan(promise: promise)
      }
    }.runOnQueue(.main)

    AsyncFunction("cancel") { (promise: Promise) -> Void in
      Task { @MainActor in
        self.cancelScan()
        promise.resolve()
      }
    }.runOnQueue(.main)

    OnDestroy {
      self.lifetimeLock.lock()
      self.runtimeDestroyed = true
      self.lifetimeLock.unlock()
      Task { @MainActor in
        // Never invoke a resolver belonging to the destroyed JavaScript runtime.
        self.pendingPromise = nil
        self.requestID = nil
        self.isSettling = false
        self.clearActivationWait()
        if #available(iOS 17.0, *),
           let controller = self.activeController as? OraRoomCaptureController {
          controller.abandon()
        }
        self.activeController?.dismiss(animated: false)
        self.activeController = nil
      }
    }
  }

  private var isRuntimeAlive: Bool {
    lifetimeLock.lock()
    defer { lifetimeLock.unlock() }
    return !runtimeDestroyed
  }

  private static func availability() -> [String: Any] {
    var result: [String: Any] = [
      "supported": false,
      "reason": "requires_ios17",
      "camera_permission": cameraPermission()
    ]
    guard #available(iOS 17.0, *) else { return result }
    #if targetEnvironment(simulator)
    result["reason"] = "requires_lidar"
    #else
    let supported = RoomCaptureSession.isSupported
    result["supported"] = supported
    result["reason"] = supported ? "supported" : "requires_lidar"
    #endif
    return result
  }

  private static func cameraPermission() -> String {
    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized: return "authorized"
    case .notDetermined: return "not_determined"
    case .denied: return "denied"
    case .restricted: return "restricted"
    @unknown default: return "restricted"
    }
  }

  @MainActor
  private func beginScan(promise: Promise) {
    guard isRuntimeAlive else { return }
    guard pendingPromise == nil else {
      promise.reject("ERR_ROOMPLAN_BUSY", "È già aperta una scansione. Completala o annullala prima di riprovare.")
      return
    }
    guard #available(iOS 17.0, *), Self.availability()["supported"] as? Bool == true else {
      promise.reject("ERR_ROOMPLAN_UNSUPPORTED", "Per scansionare servono iOS 17 o successivo e un iPhone o iPad con LiDAR.")
      return
    }
    guard let cameraUsage = Bundle.main.object(forInfoDictionaryKey: "NSCameraUsageDescription") as? String,
          !cameraUsage.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      promise.reject("ERR_ROOMPLAN_CONFIGURATION", "L'accesso alla fotocamera non è configurato in questa versione di ORA. Aggiorna l'app.")
      return
    }

    let identifier = UUID()
    requestID = identifier
    pendingPromise = promise
    isSettling = false

    switch AVCaptureDevice.authorizationStatus(for: .video) {
    case .authorized:
      presentScanner(request: identifier)
    case .notDetermined:
      AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
        Task { @MainActor in
          guard let self, self.requestID == identifier else { return }
          if granted {
            self.presentScanner(request: identifier)
          } else {
            self.settle(request: identifier, result: .failure(Self.cameraDenied))
          }
        }
      }
    case .denied, .restricted:
      settle(request: identifier, result: .failure(Self.cameraDenied))
    @unknown default:
      settle(request: identifier, result: .failure(Self.cameraDenied))
    }
  }

  private static var cameraDenied: OraRoomPlanFailure {
    OraRoomPlanFailure(
      code: "ERR_ROOMPLAN_CAMERA_PERMISSION",
      message: "Consenti l'accesso alla fotocamera in Impostazioni > ORA, poi riprova la scansione."
    )
  }

  @MainActor
  @available(iOS 17.0, *)
  private func presentScanner(request: UUID) {
    guard isRuntimeAlive, requestID == request, !isSettling else { return }
    // The first camera-permission callback can arrive while the system prompt
    // is dismissing. Wait for activation instead of falsely failing permission.
    if UIApplication.shared.applicationState == .inactive {
      guard activationObserver == nil else { return }
      activationObserver = NotificationCenter.default.addObserver(
        forName: UIApplication.didBecomeActiveNotification,
        object: nil,
        queue: .main
      ) { [weak self] _ in
        Task { @MainActor in
          guard let self, self.requestID == request else { return }
          self.clearActivationWait()
          self.presentScanner(request: request)
        }
      }
      let work = DispatchWorkItem { [weak self] in
        Task { @MainActor in
          self?.settle(request: request, result: .failure(OraRoomPlanFailure(
            code: "ERR_ROOMPLAN_INTERRUPTED",
            message: "Riapri ORA e avvia di nuovo la scansione."
          )))
        }
      }
      activationTimeout = work
      DispatchQueue.main.asyncAfter(deadline: .now() + 15, execute: work)
      return
    }
    guard UIApplication.shared.applicationState == .active else {
      settle(request: request, result: .failure(OraRoomPlanFailure(
        code: "ERR_ROOMPLAN_INTERRUPTED",
        message: "Riapri ORA e avvia la scansione tenendo l'app in primo piano."
      )))
      return
    }
    guard let presenter = appContext?.utilities?.currentViewController(),
          presenter.viewIfLoaded?.window != nil,
          !presenter.isBeingDismissed,
          !presenter.isBeingPresented else {
      settle(request: request, result: .failure(OraRoomPlanFailure(
        code: "ERR_ROOMPLAN_BUSY",
        message: "Attendi che la schermata sia aperta, poi avvia di nuovo la scansione."
      )))
      return
    }

    let controller = OraRoomCaptureController { [weak self] result in
      self?.settle(request: request, result: result)
    }
    controller.modalPresentationStyle = .fullScreen
    controller.isModalInPresentation = true
    activeController = controller
    presenter.present(controller, animated: true)
  }

  @MainActor
  private func cancelScan() {
    guard let request = requestID, !isSettling else { return }
    if #available(iOS 17.0, *), let controller = activeController as? OraRoomCaptureController {
      controller.cancel()
    } else {
      settle(request: request, result: .failure(.cancelled))
    }
  }

  @MainActor
  private func settle(request: UUID, result: Result<[String: Any], OraRoomPlanFailure>) {
    guard isRuntimeAlive, requestID == request, pendingPromise != nil, !isSettling else { return }
    isSettling = true
    clearActivationWait()
    let complete: () -> Void = { [weak self] in
      guard let self, self.isRuntimeAlive, self.requestID == request, let promise = self.pendingPromise else { return }
      self.pendingPromise = nil
      self.requestID = nil
      self.activeController = nil
      self.isSettling = false
      switch result {
      case .success(let capture): promise.resolve(capture)
      case .failure(let failure): promise.reject(failure.code, failure.message)
      }
    }
    if let controller = activeController, controller.presentingViewController != nil {
      // Keep the request busy until dismissal finishes to avoid presenting a
      // second camera controller while the previous one is still on screen.
      controller.dismiss(animated: UIApplication.shared.applicationState == .active, completion: complete)
    } else {
      complete()
    }
  }

  @MainActor
  private func clearActivationWait() {
    if let observer = activationObserver { NotificationCenter.default.removeObserver(observer) }
    activationObserver = nil
    activationTimeout?.cancel()
    activationTimeout = nil
  }
}
