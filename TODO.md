### TODO for the project

### fenetre.cam main website
- Create an index.html page with
    - Link to example deployments
    - Link to repo on github

### Github README.md
- Installation steps
  - via pip
  - via docker
- Tested hardware
- Tested picture sources


### Daylight
- On the daylight.html, there should be a top banner saying: average color of the sky for {camera_name}. Also a link to come back to the camera view

### Views
- Refine UX. List of view:
  - index with redirect to selected view
  - fullscreen
    - window title. From config file, otherwise take hostname
    - favicon
  - map
  - list
    - On the list view, there should be a details button that unfold information about the camera:
      - Link to original URL
      - Polling frequency
      - The status button should be based on the polling interval for that camera instead o fbeing hardcoded to N minutes.
  - camera details
    - Add to yesterday timelapse link
    - Uniformize the behaviour of the camera details page wheter we come from the map view, the list view and the fullscreen view.
  - daylight year
  - daylight month
  - directory browser

- Add a camera details view for deployments with a single camera
- If multiple cameras, add a link back to list

### Admin interface.
- [BUG] Crop preview is broken

### Postprocessing
- Add an option for small overlay image that shows the progression of the time throughout the as a marker on top of a blue yellow gradient. The gradient will be based on the camera location if setup.
- Add an option for alternative data display on that overlay (solar power, EXIF infos, temperature, humidity)

### Raspberry Pi specific:
- Implement native libcamera python functions instead of relying on libcamera-still
- Raspberry pi zero deployment


### Testing and integration
- Working Dockerfile and docker-compose
Testing
