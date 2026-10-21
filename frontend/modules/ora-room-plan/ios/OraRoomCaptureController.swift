import ARKit
import RoomPlan
import UIKit

/// A continuous ARSession gives every room the same coordinate system. We stop
/// instead of silently resetting tracking when the app leaves the foreground;
/// resuming across interruptions would require a verified relocalization flow.
@available(iOS 17.0, *)
@MainActor
final class OraRoomCaptureController: UIViewController, RoomCaptureViewDelegate, RoomCaptureSessionDelegate {
  private enum Phase: Equatable { case preparing, scanning, processingRoom, betweenRooms, finalizing, finished }

  private var phase: Phase = .preparing
  private var completion: ((Result<[String: Any], OraRoomPlanFailure>) -> Void)?
  private var roomCaptureView: RoomCaptureView!
  private let roomBuilder = RoomBuilder(options: [])
  private var rooms: [CapturedRoom] = []
  private var roomNames: [UUID: String] = [:]
  private var buildTask: Task<Void, Never>?
  private var timeout: DispatchWorkItem?
  private var observers: [NSObjectProtocol] = []
  private var processingData = false
  private var previousIdleTimerDisabled = false
  private let titleLabel = UILabel()
  private let statusLabel = UILabel()
  private let primaryButton = UIButton(type: .system)
  private let nextButton = UIButton(type: .system)
  private let spinner = UIActivityIndicatorView(style: .medium)
  private let maxRooms = 32

  init(completion: @escaping (Result<[String: Any], OraRoomPlanFailure>) -> Void) {
    self.completion = completion
    super.init(nibName: nil, bundle: nil)
  }

  required init?(coder: NSCoder) { return nil }

  override func viewDidLoad() {
    super.viewDidLoad()
    overrideUserInterfaceStyle = .dark
    view.backgroundColor = .systemBackground
    previousIdleTimerDisabled = UIApplication.shared.isIdleTimerDisabled
    UIApplication.shared.isIdleTimerDisabled = true
    configureInterface()
    observers.append(NotificationCenter.default.addObserver(
      forName: UIApplication.willResignActiveNotification,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      Task { @MainActor in
        self?.finish(.failure(OraRoomPlanFailure(
          code: "ERR_ROOMPLAN_INTERRUPTED",
          message: "La scansione è stata interrotta. Riprova mantenendo ORA aperta per conservare l'allineamento delle stanze."
        )))
      }
    })
  }

  override func viewDidAppear(_ animated: Bool) {
    super.viewDidAppear(animated)
    if phase == .preparing { startRoom() }
  }

  override func viewDidDisappear(_ animated: Bool) {
    super.viewDidDisappear(animated)
    if phase != .finished && (isBeingDismissed || presentingViewController == nil) {
      finish(.failure(.cancelled))
    }
  }

  private func configureInterface() {
    let cancelButton = UIButton(type: .system)
    cancelButton.setTitle("Annulla", for: .normal)
    cancelButton.tintColor = .label
    cancelButton.accessibilityIdentifier = "house-scan-native-cancel"
    cancelButton.addTarget(self, action: #selector(cancelTapped), for: .touchUpInside)
    cancelButton.heightAnchor.constraint(greaterThanOrEqualToConstant: 44).isActive = true

    titleLabel.font = .preferredFont(forTextStyle: .headline)
    titleLabel.adjustsFontForContentSizeCategory = true
    titleLabel.textColor = .label
    titleLabel.setContentHuggingPriority(.defaultLow, for: .horizontal)
    let header = UIStackView(arrangedSubviews: [titleLabel, cancelButton])
    header.axis = .horizontal
    header.alignment = .center
    header.spacing = 12

    // RoomCaptureView owns Apple's real-time overlays and scan coaching.
    roomCaptureView = RoomCaptureView(frame: .zero)
    roomCaptureView.delegate = self
    roomCaptureView.captureSession.delegate = self

    statusLabel.font = .preferredFont(forTextStyle: .subheadline)
    statusLabel.adjustsFontForContentSizeCategory = true
    statusLabel.textColor = .secondaryLabel
    statusLabel.numberOfLines = 0
    statusLabel.textAlignment = .center
    statusLabel.accessibilityIdentifier = "house-scan-native-status"

    var primaryConfiguration = UIButton.Configuration.filled()
    primaryConfiguration.baseBackgroundColor = .label
    primaryConfiguration.baseForegroundColor = .systemBackground
    primaryConfiguration.cornerStyle = .large
    primaryButton.configuration = primaryConfiguration
    primaryButton.accessibilityIdentifier = "house-scan-native-finish-room"
    primaryButton.addTarget(self, action: #selector(primaryTapped), for: .touchUpInside)
    primaryButton.heightAnchor.constraint(greaterThanOrEqualToConstant: 48).isActive = true

    nextButton.setTitle("Aggiungi stanza", for: .normal)
    nextButton.tintColor = .label
    nextButton.accessibilityIdentifier = "house-scan-native-next-room"
    nextButton.addTarget(self, action: #selector(nextTapped), for: .touchUpInside)
    nextButton.heightAnchor.constraint(greaterThanOrEqualToConstant: 44).isActive = true
    nextButton.isHidden = true
    spinner.hidesWhenStopped = true

    let footer = UIStackView(arrangedSubviews: [statusLabel, spinner, primaryButton, nextButton])
    footer.axis = .vertical
    footer.spacing = 12
    for child in [header, roomCaptureView!, footer] as [UIView] {
      child.translatesAutoresizingMaskIntoConstraints = false
      view.addSubview(child)
    }
    let safe = view.safeAreaLayoutGuide
    NSLayoutConstraint.activate([
      header.topAnchor.constraint(equalTo: safe.topAnchor, constant: 8),
      header.leadingAnchor.constraint(equalTo: safe.leadingAnchor, constant: 20),
      header.trailingAnchor.constraint(equalTo: safe.trailingAnchor, constant: -20),
      roomCaptureView.topAnchor.constraint(equalTo: header.bottomAnchor, constant: 8),
      roomCaptureView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
      roomCaptureView.trailingAnchor.constraint(equalTo: view.trailingAnchor),
      roomCaptureView.bottomAnchor.constraint(equalTo: footer.topAnchor, constant: -16),
      footer.leadingAnchor.constraint(equalTo: safe.leadingAnchor, constant: 20),
      footer.trailingAnchor.constraint(equalTo: safe.trailingAnchor, constant: -20),
      footer.bottomAnchor.constraint(equalTo: safe.bottomAnchor, constant: -12)
    ])
  }

  private func startRoom() {
    guard phase == .preparing || phase == .betweenRooms, rooms.count < maxRooms else { return }
    if !rooms.isEmpty {
      guard let frame = roomCaptureView.captureSession.arSession.currentFrame else {
        statusLabel.text = "Inquadra di nuovo l'ambiente e ritocca Aggiungi stanza quando l'iPhone ha ritrovato la posizione."
        return
      }
      guard case .normal = frame.camera.trackingState else {
        statusLabel.text = "Muovi lentamente l'iPhone verso pareti già inquadrate, poi ritocca Aggiungi stanza."
        return
      }
    }
    phase = .scanning
    processingData = false
    titleLabel.text = "Stanza \(rooms.count + 1)"
    statusLabel.text = "Inquadra lentamente tutte le pareti, il pavimento, porte e finestre."
    primaryButton.setTitle("Termina stanza", for: .normal)
    primaryButton.accessibilityIdentifier = "house-scan-native-finish-room"
    primaryButton.isEnabled = true
    nextButton.isHidden = true
    spinner.stopAnimating()
    var configuration = RoomCaptureSession.Configuration()
    configuration.isCoachingEnabled = true
    roomCaptureView.captureSession.run(configuration: configuration)
  }

  @objc private func primaryTapped() {
    switch phase {
    case .scanning:
      phase = .processingRoom
      setBusy("Elaborazione della stanza…")
      scheduleTimeout()
      // Do not pause ARKit between rooms: resetting it would create unrelated
      // coordinate systems and an apparently valid but misaligned floor plan.
      roomCaptureView.captureSession.stop(pauseARSession: false)
    case .betweenRooms:
      finalizeCapture()
    default:
      break
    }
  }

  @objc private func nextTapped() { startRoom() }
  @objc private func cancelTapped() { cancel() }

  func cancel() { finish(.failure(.cancelled)) }

  func abandon() {
    completion = nil
    finish(.failure(.cancelled))
  }

  private func setBusy(_ text: String) {
    statusLabel.text = text
    primaryButton.isEnabled = false
    nextButton.isHidden = true
    spinner.startAnimating()
  }

  private func scheduleTimeout() {
    timeout?.cancel()
    let work = DispatchWorkItem { [weak self] in
      Task { @MainActor in
        self?.finish(.failure(OraRoomPlanFailure(
          code: "ERR_ROOMPLAN_PROCESSING",
          message: "La scansione non ha terminato l'elaborazione. Riprova con una stanza alla volta e una buona illuminazione."
        )))
      }
    }
    timeout = work
    DispatchQueue.main.asyncAfter(deadline: .now() + 90, execute: work)
  }

  private func handleEnd(data: CapturedRoomData, error: Error?) {
    guard phase != .finished else { return }
    if let error {
      finish(.failure(captureFailure(error)))
      return
    }
    guard phase == .processingRoom, !processingData else {
      if phase == .scanning {
        finish(.failure(OraRoomPlanFailure(
          code: "ERR_ROOMPLAN_CAPTURE",
          message: "La scansione si è fermata prima di acquisire la stanza. Riprova muovendo lentamente l'iPhone."
        )))
      }
      return
    }
    processingData = true
    let builder = roomBuilder
    buildTask = Task { @MainActor [weak self] in
      do {
        let room = try await builder.capturedRoom(from: data)
        guard !Task.isCancelled, let self, self.phase == .processingRoom else { return }
        self.timeout?.cancel()
        self.buildTask = nil
        guard !room.walls.isEmpty else {
          self.finish(.failure(OraRoomPlanFailure(
            code: "ERR_ROOMPLAN_EMPTY",
            message: "Non sono state rilevate pareti. Riprova inquadrando l'intera stanza con più luce."
          )))
          return
        }
        self.rooms.append(room)
        self.roomNames[room.identifier] = "Stanza \(self.rooms.count)"
        self.phase = .betweenRooms
        self.titleLabel.text = self.rooms.count == 1 ? "1 stanza acquisita" : "\(self.rooms.count) stanze acquisite"
        self.statusLabel.text = "Puoi salvare oppure raggiungere la stanza successiva mantenendo l'iPhone rivolto verso l'ambiente."
        self.primaryButton.setTitle("Salva piantina", for: .normal)
        self.primaryButton.accessibilityIdentifier = "house-scan-native-save"
        self.primaryButton.isEnabled = true
        self.nextButton.isHidden = self.rooms.count >= self.maxRooms
        self.spinner.stopAnimating()
      } catch {
        guard !Task.isCancelled else { return }
        self?.finish(.failure(OraRoomPlanFailure(
          code: "ERR_ROOMPLAN_PROCESSING",
          message: "Non riesco a ricostruire la stanza acquisita. Riprova inquadrando tutte le pareti."
        )))
      }
    }
  }

  private func finalizeCapture() {
    guard phase == .betweenRooms, !rooms.isEmpty else { return }
    phase = .finalizing
    setBusy("Preparazione della piantina…")
    scheduleTimeout()
    // All inputs came from one uninterrupted ARSession. No fabricated room
    // placement, guessed scale, or AI-generated dimensions enter this payload.
    let capturedRooms = rooms
    let names = roomNames
    buildTask = Task { @MainActor [weak self] in
      do {
        let finalRooms: [CapturedRoom]
        if capturedRooms.count > 1 {
          let builder = StructureBuilder(options: [])
          let structure = try await builder.capturedStructure(from: capturedRooms)
          finalRooms = structure.rooms
        } else {
          finalRooms = capturedRooms
        }
        guard !Task.isCancelled, let self, self.phase == .finalizing else { return }
        let capture = try OraRoomCaptureSerializer.capture(rooms: finalRooms, names: names)
        self.finish(.success(capture))
      } catch let failure as OraRoomPlanFailure {
        guard !Task.isCancelled else { return }
        self?.finish(.failure(failure))
      } catch {
        guard !Task.isCancelled else { return }
        self?.finish(.failure(OraRoomPlanFailure(
          code: "ERR_ROOMPLAN_PROCESSING",
          message: "Non riesco ad allineare le stanze. Riprova acquisendole nello stesso percorso, senza chiudere ORA."
        )))
      }
    }
  }

  private func finish(_ result: Result<[String: Any], OraRoomPlanFailure>) {
    guard phase != .finished else { return }
    phase = .finished
    timeout?.cancel()
    timeout = nil
    buildTask?.cancel()
    buildTask = nil
    for observer in observers { NotificationCenter.default.removeObserver(observer) }
    observers.removeAll()
    if isViewLoaded {
      roomCaptureView.captureSession.delegate = nil
      roomCaptureView.delegate = nil
      roomCaptureView.captureSession.stop(pauseARSession: true)
      roomCaptureView.captureSession.arSession.pause()
      UIApplication.shared.isIdleTimerDisabled = previousIdleTimerDisabled
      spinner.stopAnimating()
    }
    let callback = completion
    completion = nil
    callback?(result)
  }

  private func captureFailure(_ error: Error) -> OraRoomPlanFailure {
    var message = "Non riesco a completare la scansione. Riprova con più luce e muovendo lentamente l'iPhone."
    if let captureError = error as? RoomCaptureSession.CaptureError {
      switch captureError {
      case .deviceTooHot:
        message = "L'iPhone si è scaldato troppo. Lascialo raffreddare prima di riprovare."
      case .worldTrackingFailure:
        message = "Ho perso l'allineamento della stanza. Riprova inquadrando lentamente pareti e pavimento."
      case .exceedSceneSizeLimit:
        message = "L'ambiente acquisito è troppo esteso. Riprova salvando una porzione della casa alla volta."
      default:
        break
      }
    }
    return OraRoomPlanFailure(code: "ERR_ROOMPLAN_CAPTURE", message: message)
  }

  // Apple may deliver either delegate callback while stopping the view. Both
  // feed one guarded handler, so a room can only be processed and appended once.
  nonisolated func captureView(shouldPresent roomDataForProcessing: CapturedRoomData, error: Error?) -> Bool {
    Task { @MainActor [weak self] in
      self?.handleEnd(data: roomDataForProcessing, error: error)
    }
    return false
  }

  nonisolated func captureView(didPresent processedResult: CapturedRoom, error: Error?) {}

  nonisolated func captureSession(_ session: RoomCaptureSession, didEndWith data: CapturedRoomData, error: Error?) {
    Task { @MainActor [weak self] in
      self?.handleEnd(data: data, error: error)
    }
  }
}
