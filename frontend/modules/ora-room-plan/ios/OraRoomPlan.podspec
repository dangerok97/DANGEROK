Pod::Spec.new do |s|
  s.name = 'OraRoomPlan'
  s.version = '1.0.0'
  s.summary = 'Apple RoomPlan capture for ORA'
  s.description = 'Guided, on-device room capture with structured geometry for the same ORA account.'
  s.author = 'ORA'
  s.homepage = 'https://github.com/dangerok97/DANGEROK'
  s.license = { :type => 'Proprietary' }
  s.source = { :git => 'https://github.com/dangerok97/DANGEROK.git' }
  s.platforms = { :ios => '15.1' }
  s.swift_version = '5.0'
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.frameworks = 'UIKit', 'ARKit', 'AVFoundation'
  # ORA still launches on its Expo minimum iOS version; RoomPlan is gated at
  # runtime, so a missing framework on older iOS must not prevent app startup.
  s.weak_frameworks = 'RoomPlan'
  s.source_files = '**/*.swift'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES' }
end
