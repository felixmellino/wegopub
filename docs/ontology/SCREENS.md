# Screens

Interface structure proposal. Colors, typography, icons, dimensions and
other detailed design choices remain undecided. Gameplay rules belong in
`RULES.md`; step-by-step journeys belong in `WORKFLOWS.md`.

## Overall structure

- Bottom navigation: **Profile | Standings | Check in | Map | Memories**.
- Check in is the central action for adding a drink.
- Shared header: current lobby and Season, with access to lobby switching
  and the invite code.
- First opening: Profile creation. Returning players with a completed
  profile and lobby start in Standings.

## First opening: Profile creation

- Required fields: real first name, real surname and username.
- A note explains that only the username is visible to other players;
  real names and other personal information remain private.
- Create profile button.
- After profile creation, a lobby-joining screen contains an invite-code
  field and a Join lobby button.

## Profile

- Username and personal Season summary: points, rank and territories owned.
- Recent check-ins with their status and points.
- Access to private profile details, profile editing, settings and sign out.
- Other players are identified by username only throughout the interface.

## Standings

- Player leaderboard with usernames, ranks and points.
- Territory standings with their owners and competing players' points.
- The player's own rank and points are easy to find.
- Recent lobby activity and an entry to minigames when available.

## Check in

- Drink type and drink size selection.
- Camera action and captured-photo preview.
- Detected territory and current owner.
- Points summary: base points, any territory reduction and estimated total.
- Submit, Back and Cancel controls.
- Submission status and resulting points or an error message.

## Map

- City map divided into territories, showing owners and bar locations.
- Selecting a territory shows its owner, player standings, bars and
  applicable points reduction.
- Selecting a bar shows its details and a Check in action.
- A territory list provides an alternative to the map.

## Memories

- Personal visit photos arranged chronologically, with dates and bar names.
- Selecting a photo opens the corresponding visit detail.

## Visit detail

- Photo, drink type and size, date/time and territory.
- Check-in status and a breakdown of awarded points.
- Links to the relevant territory and Standings.
