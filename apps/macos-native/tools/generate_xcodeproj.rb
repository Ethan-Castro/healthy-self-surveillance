#!/usr/bin/env ruby

require "fileutils"

begin
  require "xcodeproj"
rescue LoadError
  warn "The xcodeproj gem is required. Install it with: gem install --user-install xcodeproj"
  exit 1
end

PROJECT_ROOT = File.expand_path("..", __dir__)
PROJECT_PATH = File.join(PROJECT_ROOT, "FocusBuddyMac.xcodeproj")
SOURCE_ROOT_RELATIVE = "FocusBuddyMac/FocusBuddyMac"
SOURCE_ROOT = File.join(PROJECT_ROOT, SOURCE_ROOT_RELATIVE)

def populate_group(group, absolute_path, target)
  Dir.children(absolute_path).sort.each do |entry|
    next if entry.start_with?(".")

    full_path = File.join(absolute_path, entry)
    if File.directory?(full_path)
      subgroup = group.new_group(entry, entry)
      populate_group(subgroup, full_path, target)
    else
      file_ref = group.new_file(entry)
      target.source_build_phase.add_file_reference(file_ref) if File.extname(entry) == ".swift"
    end
  end
end

FileUtils.rm_rf(PROJECT_PATH)
project = Xcodeproj::Project.new(PROJECT_PATH)
project.root_object.attributes["LastUpgradeCheck"] = "1630"

target = project.new_target(:application, "FocusBuddyMac", :osx, "15.0")
target.product_reference.name = "FocusBuddyMac.app"

target.build_configurations.each do |config|
  settings = config.build_settings
  settings["PRODUCT_BUNDLE_IDENTIFIER"] = "com.ethancastro.FocusBuddyMac"
  settings["PRODUCT_NAME"] = "FocusBuddyMac"
  settings["SWIFT_VERSION"] = "6.0"
  settings["MACOSX_DEPLOYMENT_TARGET"] = "15.0"
  settings["CURRENT_PROJECT_VERSION"] = "1"
  settings["MARKETING_VERSION"] = "0.1.0"
  settings["GENERATE_INFOPLIST_FILE"] = "YES"
  settings["INFOPLIST_KEY_CFBundleDisplayName"] = "Focus Buddy"
  settings["INFOPLIST_KEY_LSApplicationCategoryType"] = "public.app-category.productivity"
  settings["INFOPLIST_KEY_NSCameraUsageDescription"] = "Focus Buddy uses the camera for local focus reviews."
  settings["INFOPLIST_KEY_NSMicrophoneUsageDescription"] = "Focus Buddy optionally reads local sound levels for analytics."
  settings["INFOPLIST_KEY_NSAppleEventsUsageDescription"] = "Focus Buddy reads the frontmost app and window title for local context snapshots."
  settings["INFOPLIST_KEY_FOCUS_BUDDY_API_BASE_URL"] = "http://127.0.0.1:8000"
  settings["INFOPLIST_KEY_FOCUS_BUDDY_BACKEND_PORT"] = "8000"
  settings["INFOPLIST_KEY_FOCUS_BUDDY_REPO_ROOT"] = "$(SRCROOT)/../.."
  settings["CODE_SIGNING_ALLOWED"] = "NO"
  settings["LD_RUNPATH_SEARCH_PATHS"] = "$(inherited) @executable_path/../Frameworks"
  settings["ENABLE_HARDENED_RUNTIME"] = "NO"
end

source_group = project.main_group.new_group("FocusBuddyMac", SOURCE_ROOT_RELATIVE)
populate_group(source_group, SOURCE_ROOT, target)

scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(target)
scheme.set_launch_target(target)
scheme.save_as(PROJECT_PATH, "FocusBuddyMac", true)

project.save
puts "Generated #{PROJECT_PATH}"
