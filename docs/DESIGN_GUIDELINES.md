# Design guidelines: what similar apps teach WeGoPub

Research notes for the UI/UX criterion (20%). Compiled 19 November 2026 from
apps with similar mechanics. Each section lists what the reference app does,
then what it means for WeGoPub. The last section lists concrete issues found
in the current `assets/theme.css` tokens.

## Reference apps and what they map to

| WeGoPub feature | Closest reference apps |
| --- | --- |
| Drink check-in (type → size → photo → location) | Untappd, Swarm (Foursquare) |
| Required fresh photo | BeReal |
| Territory ownership on the map | Swarm mayorships, Pokémon GO gyms, Ingress control fields, Paper.io |
| Season leaderboard | Duolingo Leagues, Strava segment leaderboards |
| Territory standings ("who owns this area") | Strava Local Legends, Swarm mayorships |
| Minigames (Quiz Duel, Chug Duel, Focus) | Kahoot, QuizDuel-style turn games |

## 1. Check-in flow (Untappd, Swarm)

**What they do**
- Untappd: search the beer → select → "Check-in". A follow-up screen then
  shows what you earned (badges, venue). A design critique of Untappd calls
  that post-check-in feedback weak: it is mixed in with ads and easy to miss.
- Untappd badges level up with repeat check-ins (e.g. every fifth). Repeat
  use is driven by visible progress, not by points alone.
- Swarm 5.0 was redesigned around what usage data showed people actually
  opened: their own check-in history, the map and a stats view. The social
  feed was moved down the hierarchy.
- Lesson from Foursquare's 2014 split: removing the competitive layer
  (mayorships, badges) drove users away. Mayorships came back in 2015 by
  popular demand. The game layer *is* the product.

**For WeGoPub**
- Keep the check-in to as few screens as possible: drink type (4 large tiles)
  → size (3 tiles, skipped for Shot) → photo → submit. Location runs in the
  background, so the player never has to press a "verify location" button.
- Make the **result screen** the reward moment. It should show, in this order:
  points earned (big number), which territory got them, and whether that
  changed ownership ("You took Bairro Alto from Ana!"). It should have no
  other content competing with it.
- For a rejected check-in, say why and what to do, in one line each:
  "Location not accurate enough (120 m, needs 50 m). Step outside and try
  again." State plainly that no points were changed.
- Show the cooldown and the scoring window *before* the player starts, not
  after they took a photo ("Next check-in in 1:24", "Game night starts
  Thursday 18:00").

## 2. Required photo (BeReal)

**What they do**
- BeReal gives a 2-minute window, after which the post is labelled "late"
  rather than blocked. The time limit exists to stop people curating
  their photo.
- Capture is a single full-screen action with a large shutter button.
  BeReal shows the secondary camera as a small picture-in-picture inset.

**For WeGoPub**
- Make the camera full width with one obvious shutter button near the bottom
  of the screen. Use "Retake" and "Use photo" as the only two choices after
  capture.
- A visible "fresh photo" cue (a timestamp chip on the preview) helps the
  player understand *why* uploads from the gallery are not allowed.

## 3. Territory map (Swarm mayorships, Pokémon GO, Ingress, Paper.io)

**What they do**
- Pokémon GO and Ingress make the map the home screen, with the player's
  dot in the centre and game objects drawn over a deliberately quiet base
  map. Mapbox's guide to styling location-game maps recommends a restrained
  base palette so the game layer stands out.
- Ownership is shown by a team colour on the area or object itself, so
  the state can be read without tapping.
- Ingress's map update focused on one-handed, one-finger pan and zoom.
- Accessibility guidance for games: never convey essential information by
  colour alone, and avoid red/green as the main contrast, because red–green
  colour blindness is the most common type.

**For WeGoPub**
- Use a muted, low-saturation base map so territory fills carry the colour.
- Encode "yours / theirs / free" with **two cues**: colour plus lightness or
  pattern (e.g. solid fill for yours, hatched for theirs, outline only for
  free), and the owner's initials or avatar in the area's label.
- Tapping a territory should open a bottom card with: owner, your total there
  vs the owner's, and the gap ("3 points to take it"). This is the Local
  Legends idea applied to territories.
- Keep the HUD (your total, current territory) pinned and compact at the top;
  keep the check-in button within thumb reach at the bottom.

## 4. Leaderboards (Duolingo Leagues, Strava Local Legends)

**What they do**
- Duolingo: about 30 people per weekly league, with visible **promotion and
  demotion zones** drawn as coloured bands in the list. It also sends prompts
  when you drop out of the promotion zone or someone overtakes you.
- Strava Local Legends ranks by number of efforts in a rolling 90-day window
  rather than speed, so being consistent can win. Instead of a long list it
  shows a histogram of where *you* sit relative to the leader, so the gap is
  visible at a glance.
- Critique of both: leaderboards lose motivational power when the gap to
  the top feels impossible. Showing "your next target" works better than
  showing rank 1.

**For WeGoPub**
- Always show the player's own row, pinned or highlighted, even when they
  are off-screen.
- Next to the player's row, show the gap to the player directly above them
  ("2.5 pts behind Tomás"). That is more actionable than the absolute rank.
- Show a "↑ 2 since last night" change indicator per row; lobbies are small
  (friends), so movement is what is interesting.
- Make the tie rule visible: when two scores are equal, show a small
  "reached first" note so ranking never looks arbitrary.
- Podium styling (gold/silver/bronze) for the top 3 only; plain rows below.

## 5. Minigames (Kahoot, quiz duels)

**What they do**
- Kahoot shows answers as large coloured tiles *with a shape* (triangle,
  diamond, circle, square), so the colour is never the only cue. A countdown
  is always visible, and the result screen shows the correct answer and how
  many picked each option.
- Kahoot's accessibility mode gives everyone equal time and puts accuracy
  ahead of speed.

**For WeGoPub**
- Use 2×2 large answer tiles that cover most of the screen. They are easy to
  hit with an unsteady thumb in a bar.
- Show a countdown bar (not just a number) and immediate right/wrong feedback
  after each answer.
- End every minigame on one clear result card: won/lost, the special item or
  points received, and "You have used tonight's minigame" so the shared limit
  is understood rather than discovered as an error.
- Use our own shapes and colours; don't reproduce Kahoot's tile designs.

## 6. Context of use: a phone, in a bar, at night

General mobile guidance, applied to our setting:
- **One-handed use.** Steven Hoober's observational research found about half
  of phone interactions are one-thumbed. Put frequent actions (check in, take
  photo, answer) in the bottom half and rare or destructive ones (log out,
  delete) further away. (Some designers say thumb-zone maps are only a
  heuristic, so treat this as a rule of thumb, not a law.)
- **Touch targets** at least 44 pt (Apple) / 48 dp (Material). Our primary
  buttons are 52 px and secondary ones 44 px, which meets this.
- **Low light.** A bright white screen in a dark bar is harsh. Consider a
  dark theme that follows the phone's system setting. Dark themes still need
  4.5:1 text contrast, so don't use mid-grey text on dark grey.
- **Glanceability.** Every screen should answer one question within a second:
  "How many points do I have?", "Who owns this area?", "Did my drink count?".
- **Forgiving input.** Large tiles instead of dropdowns, no typing during the
  core loop, a clear way to undo or retake.

## 7. Contrast issues found, and what UI batch 3 fixed

Contrast ratios computed with the WCAG 2.x formula. All fixed on branch
`ui-polish-batch-3` (19 November 2026):

| Issue | Before | After |
| --- | --- | --- |
| Territory colours were green/red (off-palette, red-green colour-blind risk) | #4CC38A / #FF5D52 | Sky #2C99D6 = yours, Scarlet #EB2F33 = theirs, grey #8A97A6 = free |
| Green "yours" score used as small text on the white HUD | 2.2:1 | `--territory-yours-ink` (#156A96) 5.9:1 |
| `--text-muted` on the page background | 4.28:1 | #52708A, 4.96:1 |
| `--success` used as small text (history award) | 3.41:1 | `--success-ink` #1F7A45, 4.79:1 on the soft-blue pill |
| Background was not Cloud White | #F4F9FC | #F8FAFC |
| Map "you are here" dot was blue, same as the new "yours" fill | #5AA8FF | White dot, navy ring |

Rule going forward: when a colour token is used as small text, use its
`-ink` shade (`--accent-ink`, `--brand-ink`, `--territory-*-ink`,
`--success-ink`).

## Sources

- Untappd design critique: https://ixd.prattsi.org/2019/09/design-critique-untappd-android-app/
- Untappd badges: https://help.untappd.com/hc/en-us/articles/360033785812 and https://en.wikipedia.org/wiki/Untappd
- Untappd engagement: https://www.braze.com/resources/articles/engage-millions-users-mobile-community-building-lessons-untappd
- Swarm 5.0 redesign: https://medium.com/foursquare-direct/d774b3164f3f
- Mayorships return: https://www.droid-life.com/2015/06/22/swarm-gets-mayorships-like-it-had-when-it-was-relevant-as-foursquare/
- De-gamification of Foursquare: https://nextconf.eu/2014/08/the-de-gamification-of-foursquare/
- Strava Local Legends: https://www.bikeradar.com/news/strava-local-legend/ and https://9to5mac.com/2020/06/10/strava-local-legends-leaderboard/
- Duolingo leagues analysis: https://duolingo.deconstructoroffun.com/mechanics/leagues and https://mattmecham.substack.com/p/what-a-one-year-streak-in-duolingo-taught-me-about-community-gamification
- BeReal: https://en.wikipedia.org/wiki/BeReal
- Pokémon GO map view: https://niantic.helpshift.com/hc/en/6-pokemon-go/faq/84-map-view/
- Ingress map UI: https://techcrunch.com/2018/11/05/what-is-ingress-prime/amp/
- Location-game map styling: https://blog.mapbox.com/design-a-location-based-game-map-with-mapbox-studio-8cf47528fa80
- Colour in games: https://gameaccessibilityguidelines.com/ensure-no-essential-information-is-conveyed-by-a-fixed-colour-alone/
- Kahoot: https://kahoot.com/how-to-play-kahoot/ and https://kahoot.com/accessibility/
- One-handed use: https://shop.smashingmagazine.com/2020/02/design-mobile-apps-one-hand-usage/ and https://addyosmani.com/blog/touch-friendly-design/
- Dark mode: https://blog.logrocket.com/ux-design/dark-mode-ui-design-best-practices-and-examples/

Most sources are press coverage and third-party analyses rather than the
companies' own documentation, and some describe features at launch (e.g.
Local Legends in 2020). Check the current apps before copying a detail.
