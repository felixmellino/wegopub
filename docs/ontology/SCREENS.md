# Screens

## Status and scope

UI proposal for team review, not an agreed game specification. Based on
`README.md` and the core workflow in `AGENTS.md`. The other ontology files
are currently placeholders. Screen names and flows below are proposals;
scoring, eligibility and ownership must ultimately come from `RULES.md`.

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
and the invite code behind the lobby name, and a confirmation inbox behind
a bell with a pending-count badge. A game-night status names the relevant
date and timezone; exact hours depend on the team's boundary decision.

## Screens and actions

### Profile

- Show avatar, display name, current Season points, rank, territories led
  and confirmed visits. Label all totals with their time period.
- Show recent personal check-ins with their status and awarded points.
- Allow opening a visit, editing the profile, opening settings and signing out.
- Put account/privacy settings here rather than in another bottom tab.

### Standings (default destination)

- Lead with the player's rank and confirmed Season points.
- Show the individual leaderboard, highlighting the player even when they
  are outside the visible leaders. Each row opens that player's public profile.
- Provide a local switch between Players and Territories. Territory rows
  show the current leader and open the same detail used by the map.
- Show pending buddy requests near the top with a direct Review action.
- Include a short lobby activity list for confirmed visits and territory
  leadership changes, with links to the relevant visit or territory.
- Offer a Games entry here once one minigame is working. It shows whether
  the player's shared game-night allowance is available or used across
  all games and arenas; it does not need a sixth navigation item.

### Check in (central action)

1. Select a bar. Suggest nearby bars if location permission is granted,
   but make the chosen bar explicit before submission.
2. Capture a photo and review it. The README's drink details and upload
   alternatives need team agreement before becoming required inputs.
3. Select a buddy and review the bar, photo and any required details.
4. Submit once and show a visit detail marked **Pending buddy confirmation**.

Do not display pending points as awarded. After confirmation, show the
actual points awarded and links to Standings and the territory detail.
Explain camera/location permission problems with a retry action; any
alternative verification method requires an agreed rule. Preserve entered
details on recoverable failures and prevent accidental repeat submissions.
Server validation remains authoritative for eligibility and scoring.

### Confirmation inbox and visit detail

- Inbox: requests awaiting this player's review, each showing the player,
  bar, visit time, photo and status. Open a request to inspect its details.
- Detail: offer Confirm for eligible requests. Whether buddies can reject
  or report requests, and what happens next, remains a team decision.
- Explain self-confirmation, duplicate confirmation, stale requests and
  other invalid actions. Rejected actions leave points unchanged.
- On success, show the updated visit status. Opening an already processed
  request shows its current status rather than another active Confirm button.
- Link the submitter's pending visit from Profile and Standings so they
  can find it again after leaving the submission flow.

### Map and territory detail

- Show territory boundaries, owner/leader labels and bar markers. Pair
  player colors with names or initials; color alone must not convey ownership.
- Selecting a territory opens a detail panel with its leader, competing
  players' points and constituent bars. Selecting a bar opens its details
  and offers Check in with that bar preselected.
- Offer a list alternative showing the same territory standings if the
  map cannot load or is difficult to use.
- Use a neutral label for an unclaimed or tied territory only when its
  meaning is defined by the agreed ownership and tie rules.
- Display bar locations and territory ownership; live player tracking is
  outside this proposal.

### Memories

- Show a chronological grid of the player's visit photos, grouped by date,
  with bar names. Open a photo to see its visit detail and status.
- Keep pending and confirmed visits distinguishable wherever both appear.
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
- After each action, name its outcome: pending confirmation, confirmed with
  points awarded, or rejected with a reason. Include text alongside status icons.
- Refresh affected standings and territory details after confirmation;
  show when a displayed result is stale or could not be refreshed.

## Build order and open decisions

1. Profile/join lobby → check in → buddy confirmation → updated Standings
   and territory detail. A territory list can precede the interactive map.
2. Interactive map and personal Memories using the same visit records.
3. One minigame with a shared allowance across games and arenas.

Before implementing dependent behavior, agree night boundaries/timezone,
scoring, repeat visits, ties, territory ownership/reset rules, buddy
eligibility/request expiry, photo and location requirements, photo privacy,
and interrupted minigames. The README's automatic photo/GPS capture idea
also needs alignment with the buddy-confirmed core in `AGENTS.md`.

For the four-position navigation alternative, use **Profile | Standings |
Check in | Map**, placing Memories inside Profile. Five positions make
the photo feature easier to discover; four reduce the initial build scope.
