### TODO for the project

### fenetre.cam main website
- The main site should load a map by default with all the links to public deployments
- There should be a link to the github

### Github README.md
- Installation steps
  - via pip
  - via docker
- Tested hardware
- Tested picture sources


### Main module
- Check if an instance is already running with the exact same config and prevent starting again

### Daylight
- On the daylight.html, there should be a top banner saying: average color of the sky for {camera_name}. Also a link to come back to the camera view

### Config checker
- config.example.yaml isn't enough. The config.py should document and sanity check the entire config.

### Views
- Refine UX. List of view:
  - fullscreen
    - window title. From config file, otherwise take hostname
  - map
  - list
    - On the list view, there should be a details button that unfold information about the camera:
      - Polling frequency
      - The status button should be based on the polling interval for that camera instead o fbeing hardcoded to N minutes.
  - camera details
  - Uniformize the behaviour of the camera details page wheter we come from the map view, the list view and the fullscreen view.
  - Add a about page with links to Github, the main fenetre.cam and the code version
- Add a hall of fame

### Admin interface.
- [BUG] Crop preview is broken (not to scale)
- ssim and sky area should be defiend on the crop preview since they happen after crop
- Add the ability to pin a picture to a hall of fame

### Postprocessing
- Add an option for small overlay image that shows the progression of the time throughout the as a marker on top of a blue yellow gradient. The gradient will be based on the camera location if setup.
- Add an option for alternative data display on that overlay (solar power, EXIF infos, temperature, humidity)

### Raspberry Pi specific:
- Implement native libcamera python functions instead of relying on libcamera-still
- Raspberry pi zero deployment

### Testing and integration
- Working Dockerfile and docker-compose
- Add integration test simulating a few days worth of pictures

### Metrics
- Add version 
