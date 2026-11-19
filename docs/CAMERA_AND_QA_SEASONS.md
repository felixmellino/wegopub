# Instant camera and QA seasons

The central + opens Check-in and starts the camera and phone GPS together.
Browser permission is still required. `camera_capture.py` is the Streamlit
bridge to `components/drink_camera/index.html`; it replaces the native
camera widget's separate enable step without automating browser prompts.

The camera has its own full-viewport stage: a rear-camera preview, bottom-centre
circular shutter, front/back switch and close button. It uses no microphone.
Browser chrome and permission prompts remain controlled by the browser; this
is an in-app camera, not a launch of the phone's native Camera application.
Single-camera devices may return the same camera for either preference.

Taking the photo automatically leaves the camera stage and opens the form,
with a rounded photo preview, Retake, drink/size controls, location and Submit.
The JPEG matches the preview's centre crop (including front-camera mirroring),
and is at most 1600 pixels on its longest edge. Capture, switching cameras,
closing, backgrounding and navigation stop the old media stream, including
late permission responses. Retake opens a fresh full-screen camera.

Validated pending photos live only in the signed-in Streamlit session and
are bound to player, membership and season. GPS reruns retain that photo and
submission ID without remounting the camera. Retake or a context change clears
the old capture; a server restart loses an unsaved photo. Nothing is uploaded
until Submit. Success clears pending bytes and keeps the receipt visible;
New check-in or the navigation + explicitly starts another capture.

The server validates the base64 transport and capture UUID, applies the
existing byte/pixel/decode limits, strips metadata and retains a stable
capture identity across GPS reruns. Existing submission, lost-reply recovery,
cooldown and access checks remain in place. No additional package is required.

## Enable Wednesday testing

Create a **new QA lobby** and check **Test season: Wednesday 08:00–Sunday
18:00** before submitting Create lobby. The checkbox defaults to off. An
incomplete setup also exposes that choice under Retry lobby setup. The
lobby card and Check-in page label test seasons visibly for all members.

The normal points table is used; only the opening day/hour changes. The
choice is part of the existing frozen JSON rules snapshot sent to the
season-creation RPC. The existing database scoring-window function reads
that snapshot, so **no new migration is required**. Existing seasons,
normal-season defaults and minigame night rules remain unchanged. Test
points stay inside the separate QA lobby. Never change the server clock
or edit an active season's snapshot to enable testing.

QA seasons also allow unlimited sequential Chug Duel replays after migration
012 (R-M02). Minigames shows Unlimited for both roles, including after an
earlier win or abort. The frozen boolean test flag controls this, not the
lobby's name. Finish/end the active game before another; photo/GPS, ordinary
two-minute check-in cooldown, scoring window and scoring rules still apply.
The ordinary Wednesday-window setting itself needs no extra migration;
unlimited minigame attempts require 012 after 011.

## Verification

Run the normal Python suite with `python -m pytest -q`.
`tests/test_camera_capture.py` checks transport validation and metadata removal;
`tests/test_test_seasons.py` checks exact cutoffs, timezone behavior and the
frozen database payload. Streamlit AppTests exercise creating both kinds of
season and starting location before capture.

`node tests/camera_component.cjs` checks the actual camera JavaScript with
synthetic media objects: automatic opening, no reopen on GPS rerenders,
capture/crop/mirroring, front/back switch, close, permission denial/retry, navigation and background cancellation.
It never requests a real camera. The optional isolated PostgreSQL suite in
`tests/scoring_postgres.cjs` also checks the server's Wednesday 08:00/Sunday
18:00 boundaries and QA-rule persistence after restart; see
`docs/SCORING_IMPLEMENTATION.md` for setup.

A synthetic browser preview can verify the interface, but real iPhone/Android
camera permission, video startup and GPS still need the deployed HTTPS app.
On a phone: open +, grant permissions, take a photo, check its preview and
location, choose drink/size and submit in a QA lobby. Check that Retake and
leaving/backgrounding the page stop the old camera stream.
