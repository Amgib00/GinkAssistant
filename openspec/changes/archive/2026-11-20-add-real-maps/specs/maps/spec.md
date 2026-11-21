## ADDED Requirements

### Requirement: Real maps in answers
When an answer is about real places, the chat (apps and web app) SHALL show a street map drawn on the device from OpenStreetMap data in Gink's own style, light or dark like the app, with each place marked, numbered and named, and the map's own names making room for them; there SHALL be no button to press.

#### Scenario: Museums in a city
- **WHEN** an answer about three museums ends with a map block
- **THEN** a street map appears in its place with three numbered, named markers and three place cards

#### Scenario: Dark mode
- **WHEN** the person switches Gink to dark while a map is shown
- **THEN** the map redraws in the dark style with the same places

### Requirement: Place cards
Each place SHALL have a card under the map with its number, name, kind (from the answer's category, or guessed from its name and note), note, a photo when one exists, and Directions that open Apple Maps on Apple devices and Google Maps elsewhere. Choosing a card SHALL move the map to that place; choosing a marker SHALL highlight its card.

#### Scenario: A café without a category
- **WHEN** a place called "Café Sprüngli" comes without a category
- **THEN** its card says Café and its marker has the café colour

#### Scenario: Directions
- **WHEN** someone on Windows taps Directions on a card
- **THEN** Google Maps opens with directions to that place's coordinates

### Requirement: Map data through Gink's server
The map library, style, tiles, letters and place photos SHALL come from Gink's server, cached there and limited per address, so the device never contacts the map or photo services itself; the map SHALL always show "© OpenStreetMap" with OpenMapTiles and OpenFreeMap credits.

#### Scenario: Many pieces from one address
- **WHEN** one address asks for more than 2,400 map pieces in ten minutes
- **THEN** the server answers 429 until the window passes

### Requirement: Picture-square fallback
A device that can't draw vector maps (no WebGL, very little memory, an older browser) or a server without them SHALL get the picture-square map with the same markers and cards.

#### Scenario: No WebGL
- **WHEN** a map appears on a device without WebGL
- **THEN** the picture-square map shows the same numbered places and cards

### Requirement: Calm gestures and a bigger map
Scrolling the chat over a map SHALL scroll the chat (⌘ or Ctrl + scroll, or two fingers on a touch screen, moves the map); a button SHALL open the map bigger over the chat, where plain scrolling zooms, and Esc or the button SHALL close it.

#### Scenario: Scrolling past a map
- **WHEN** someone scrolls the chat with the pointer over a map
- **THEN** the chat scrolls and the map says to use ⌘ + scroll (Ctrl + scroll on other computers) to zoom

### Requirement: Maps for developers
Answers asked with `gink_maps` SHALL include each place's category; `/v1/places/photo` SHALL return a place's picture or 404; the Python and JavaScript SDKs SHALL return `category` from `maps()` and offer `place_photo` / `placePhoto`; `gink map --photos` SHALL print a photo link for each place.

#### Scenario: A place with no picture
- **WHEN** a developer asks `/v1/places/photo` for a place with no Wikipedia picture
- **THEN** the API answers 404 with the code `not_found` and the SDKs return None / null
