[app]
title = Hazmat Driver
package.name = hazmatdriver
package.domain = org.hazmat

# Entry point
source.dir = .
source.main = DriverApp.py

# Include app assets
source.include_exts = py,png,jpg,kv
source.include_patterns = static/*

# App requirements (leaner set)
requirements = python3,kivy,requests,numpy,plyer,geopy,pyzbar,kivy_garden.mapview,fastapi,starlette,pydantic,annotated-types,typing-extensions,anyio,h11,idna,sniffio


orientation = portrait
fullscreen = 0

# Permissions for GPS/camera/network
android.permissions = INTERNET, ACCESS_NETWORK_STATE, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION, CAMERA

# Target API levels
android.api = 30
android.minapi = 24

# (Optional) App version
version = 0.1

# (Optional) icon
# icon.filename = static/logo.png

[buildozer]
log_level = 2
warn_on_root = 0
