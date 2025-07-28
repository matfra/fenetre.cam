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

### Testing and integration
- Working Dockerfile and docker-compose
Testing
- Raspberry pi zero deployment

### Daylight
- On the daylight.html, there should be a top banner saying: average color of the sky for {camera_name}. Also a link to come back to the camera view

### Views
- Refine UX. List of view:
  - index with redirect to selected view
  - fullscreen
    - window title
    - favicon
  - map
  - list
  - camera details
  - daylight year
  - daylight month
  - directory browser

- Add a camera details view for deployments with a single camera
- If multiple cameras, add a link back to list

### Postprocessing
- Add an option for overlay that shows the progression of the day with blue yellow gradient
  - Add an option for alternative data display on that overlay (solar power, EXIF infos, temperature, humidity)

UI:
On the list view, there should be a details button that unfold information about the camera:
- Link to original URL
- Polling frequency

The status button should be based on the polling interval for that camera instead o fbeing hardcoded to N minutes.

- Add to yesterday timelapse link

Cliking on the picture from unfolded list view should pull up the fullscreen mode.