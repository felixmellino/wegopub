# Screens

## Status and scope

UI proposal for team review, not an agreed game specification. Based on
`README.md` and the updated direction recorded in `RULES.md`: automatic
photo/location verification replaces buddy confirmation. Screen names and
flows below are proposals; exact scoring and boundaries remain open in
`OPEN_DECISIONS.md`.

## Bottom navigation

Keep five positions in this order on mobile:

| Position | Label / icon | Purpose |
| --- | --- | --- |
| 1 | Profile / user | Personal progress, visit history and settings |
| 2 | Standings / trophy | Season leaderboard, territory standings and lobby activity |
| 3 | Check in / plus | Start a visit submission; a prominent action rather than a destination |
| 4 | Map / map | Explore territories, their leaders and their bars |
| 5 | Memories / images | Browse the player's visit photos |

Use visible labels with icons, a clear selected destination, and touch
targets of at least 44 × 44 px. The plus opens a focused flow with Back
and Cancel; it does not change the selected destination underneath.
Preserve each destination's position when switching tabs.

Open Standings after login: it explains the competition and gives a
useful starting point each night. First-time users create a profile and
join a lobby using an invite code before entering the main interface.

The shared header shows the current lobby and Season. Put lobby switching
and the invite code behind the lobby name. A game-night status names the relevant
date and timezone; exact hours depend on the team's boundary decision.

## Screens and actions

### Profile

- Show avatar, display name, current Season points, rank, territories led
  and accepted visits. Label all totals with their time period.
- Show recent personal check-ins with their status and awarded points.
- Allow opening a visit, editing the profile, opening settings and signing out.
- Put account/privacy settings here rather than in another bottom tab.

### Standings (default destination)

- Lead with the player's rank and awarded Season points.
- Show the individual leaderboard, highlighting the player even when they
  are outside the visible leaders. Each row opens that player's public profile.
- Provide a local switch between Players and Territories. Territory rows
  show the current leader and open the same detail used by the map.
- Include a short lobby activity list for accepted visits and territory
  leadership changes, with links to the relevant visit or territory.
- Offer a Games entry here once one minigame is working. It shows whether
  the player's shared game-night allowance is available or used across
  all games and arenas; it does not need a sixth navigation item.

### Check in (central action)

1. Select drink type and size from the configured scoring table.
2. Take the required photo. Recommended: collect current phone location at
   capture time; inspect embedded photo coordinates when available.
3. Show the detected territory, current owner, base points, any non-owner
   reduction and estimated final points. Explain why a reduction applies.
4. Submit once. Show **Verifying location** while processing, then either
   **Accepted · points awarded** or an actionable failure reason.

The server determines the territory and final score. The preview may change
if ownership changes before acceptance. Missing/uncertain location must not
silently produce points. Explain camera/location permission problems and
provide retry actions. Preserve entered details on recoverable failures.

### Visit detail

- Show photo, drink type, size, time, territory and processing status.
- For accepted visits, show base points, applied reduction and final points;
  link to Standings and the territory detail, including any ownership change.
- For failed verification, explain the reason; points remain unchanged.
- Make processing visits accessible from Profile so a network interruption
  does not require another submission. A retry must not duplicate awards.
- Automatic location checks do not prove the declared drink or size is correct.

### Map and territory detail

- Show territory boundaries, owner/leader labels and bar markers. Pair
  player colors with names or initials; color alone must not convey ownership.
- Selecting a territory opens a detail panel with its owner, competing
  players' points, applicable non-owner reduction and constituent bars. Selecting a bar opens its details
  and offers Check in; territory assignment still comes from verified location.
- Offer a list alternative showing the same territory standings if the
  map cannot load or is difficult to use.
- Use a neutral label for an unclaimed or tied territory only when its
  meaning is defined by the agreed ownership and tie rules.
- Display bar locations and territory ownership; live player tracking is
  outside this proposal.

### Memories

- Show a chronological grid of the player's visit photos, grouped by date,
  with bar names. Open a photo to see its visit detail and status.
- Distinguish processing, accepted and failed visits wherever they appear together.
- Start with a personal gallery. Sharing, visibility and deletion behavior
  need decisions before adding controls that promise those actions.
- Empty state: explain that photos from submitted visits appear here and
  offer Check in. A failed image load must not hide the visit's text details.

## Presentation and feedback

- Use a restrained interface: neutral backgrounds, one accent for primary
  actions, and consistent player colors on the map and in standings.
- Keep the bottom navigation stable and clear of the phone's safe area.
  On wider screens, the same destinations can move to a side navigation.
- Show loading, empty, unavailable and retry states for every data screen.
  Distinguish a failed request from a successful request with no results.
- After each action, name its outcome: verifying location, accepted with
  points awarded, or rejected with a reason. Include text alongside status icons.
- Refresh affected standings and territory details after acceptance;
  show when a displayed result is stale or could not be refreshed.

## Build order and open decisions

1. Profile/join lobby → drink/size/photo → location verification → updated Standings
   and territory detail. A territory list can precede the interactive map.
2. Interactive map and personal Memories using the same visit records.
3. One minigame with a shared allowance across games and arenas.

Before implementing dependent behavior, resolve `OPEN_DECISIONS.md`, especially
location acceptance, drink/size scoring, the ownership reduction, ties,
repeat visits and game-night boundaries. Keep scoring in one shared rules
module so the preview, final award and standings stay consistent.

For the four-position navigation alternative, use **Profile | Standings |
Check in | Map**, placing Memories inside Profile. Five positions make
the photo feature easier to discover; four reduce the initial build scope.
