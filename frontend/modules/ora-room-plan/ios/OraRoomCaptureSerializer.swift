import Foundation
import RoomPlan
import simd

@available(iOS 17.0, *)
enum OraRoomCaptureSerializer {
  static func capture(rooms: [CapturedRoom], names: [UUID: String]) throws -> [String: Any] {
    guard !rooms.isEmpty else {
      throw OraRoomPlanFailure(code: "ERR_ROOMPLAN_EMPTY", message: "La scansione non contiene stanze da salvare.")
    }
    let result: [String: Any] = [
      "schema_version": 1,
      "capture_id": UUID().uuidString.lowercased(),
      "source": "apple_roomplan",
      "captured_at": ISO8601DateFormatter().string(from: Date()),
      "rooms": try rooms.enumerated().map { index, room in
        try serialize(room: room, name: names[room.identifier] ?? "Stanza \(index + 1)")
      }
    ]
    guard JSONSerialization.isValidJSONObject(result) else { throw invalidGeometry() }
    return result
  }

  private static func serialize(room: CapturedRoom, name: String) throws -> [String: Any] {
    [
      "id": room.identifier.uuidString.lowercased(),
      "name": name,
      "walls": try room.walls.map(surface),
      "doors": try room.doors.map(surface),
      "windows": try room.windows.map(surface),
      "openings": try room.openings.map(surface),
      "floors": try room.floors.map(surface),
      "objects": try room.objects.map(object)
    ]
  }

  private static func surface(_ value: CapturedRoom.Surface) throws -> [String: Any] {
    var result: [String: Any] = [
      "id": value.identifier.uuidString.lowercased(),
      "dimensions": try dimensions(value.dimensions),
      "transform": try transform(value.transform),
      // RoomPlan confidence describes classification, not a distance error bar.
      "confidence": confidence(value.confidence)
    ]
    if !value.polygonCorners.isEmpty {
      result["polygon_corners"] = try value.polygonCorners.map(vector)
    }
    return result
  }

  private static func object(_ value: CapturedRoom.Object) throws -> [String: Any] {
    [
      "id": value.identifier.uuidString.lowercased(),
      "dimensions": try dimensions(value.dimensions),
      "transform": try transform(value.transform),
      "confidence": confidence(value.confidence),
      "category": String(describing: value.category)
    ]
  }

  private static func dimensions(_ value: SIMD3<Float>) throws -> [String: Double] {
    guard value.x >= 0, value.y >= 0, value.z >= 0 else { throw invalidGeometry() }
    return try vector(value)
  }

  private static func vector(_ value: SIMD3<Float>) throws -> [String: Double] {
    ["x": try finite(value.x), "y": try finite(value.y), "z": try finite(value.z)]
  }

  private static func transform(_ value: simd_float4x4) throws -> [Double] {
    // SIMD matrices are column-major. Keep all 16 entries, in metres, without
    // rounding or changing each room's origin. JS applies this to local points.
    try (0..<4).flatMap { column in
      try (0..<4).map { row in try finite(value[column][row]) }
    }
  }

  private static func finite(_ value: Float) throws -> Double {
    guard value.isFinite else { throw invalidGeometry() }
    return Double(value)
  }

  private static func confidence(_ value: CapturedRoom.Confidence) -> String {
    switch value {
    case .high: return "high"
    case .medium: return "medium"
    case .low: return "low"
    @unknown default: return "unknown"
    }
  }

  private static func invalidGeometry() -> OraRoomPlanFailure {
    OraRoomPlanFailure(
      code: "ERR_ROOMPLAN_PROCESSING",
      message: "La scansione contiene misure incomplete. Riprova acquisendo tutte le pareti della stanza."
    )
  }
}
