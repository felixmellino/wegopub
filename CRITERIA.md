# WeGoPub / Bar Territories

Team project for Introduction to Programming at Nova SBE. Read this
file before planning, implementing, reviewing, or documenting changes.

## Course requirements

- The team project counts for 40% of the final course grade. It is built
  in Block 3 and presented in weeks 11–12.
- Teams consist of 3–4 students. Our team has four members, and each
  member must contribute code to the repository.
- Build on one team member's Block 2 solo project. Record which project
  was selected and explain what WeGoPub reuses and extends.
- Deploy a working application at a public URL. Keep the repository
  public and the deployed source code on `main`.
- In `README.md`, include the deployed URL, all team members' names and
  student numbers, and the exact commands to run the app and tests locally.
- One team member submits the GitHub repository link to the Team Project
  assignment on Moodle by 23 November 2026 at 23:59. Commits made after
  the deadline are excluded from grading.
- Give a live demo using the deployed app. The course requires live use
  during class, so plan the demo around the working public URL.
- In the code walkthrough, every member may be questioned on code written
  by teammates. The team grade can be adjusted individually.

## What a top-scoring project should demonstrate

Each criterion has the same weight in the project grade (20%).

| Criterion | What to aim for |
| --- | --- |
| It works | Every deployed workflow runs end to end and handles invalid actions gracefully. |
| Design | Screens, game rules, and storage are clearly separated. Names and the data model make the code easy to understand and extend. |
| Scope and ambition | Meaningful new features build on the selected solo project and work together coherently. |
| Verification | Automated tests cover valid actions, rejected actions, and edge cases. The full suite passes on `main`. |
| Walkthrough | Every member can explain what the code does, why it is structured that way, and how they would change it. |

## WeGoPub priorities

1. Finish the core workflow first. A player checks in at a bar, a buddy
   confirms the visit, and the player sees the resulting points in the
   Season leaderboard and the territory standings.
2. Add one playable minigame with a shared limit of one game per player
   per game night across all games and arenas. Reuse that logic for
   additional minigames.
3. Once the core is stable, prioritize additions that make the game
   better and can be demonstrated and tested. Team events and special
   effects depend on rules agreed by the team.

The main competition is individual. Seasons last roughly one month, with
game nights from Thursday to Sunday. Bars belong to territories.
Confirm the exact night boundaries, scoring, repeat visits, ties, and
minigame interruptions before implementing behavior that depends on them.
Treat an unresolved rule as an open team decision.

## Instructions for AI assistants and contributors

- Read the relevant code, tests, and project decisions before making a
  change. Keep each change focused and connect it to the user workflow
  and course criteria it supports.
- Keep game rules in one place and use them consistently in the UI,
  rankings, and tests. Prefer simple code that all four members can explain.
- Define expected outcomes for allowed, rejected, and boundary cases.
  Add or update tests when behavior changes. Keep existing assertions
  meaningful and correct them only when the agreed rule changes.
- Run the relevant tests and verify the changed behavior through the
  app. For changes involving saved state, check that it survives a restart.
  Report the commands you ran, what passed, and what still needs checking.
- Use small, reviewable changes so each student can own real code and
  explain it to the team. In handoffs, explain where the change lives,
  why it works that way, and how a teammate can verify it.
- Flag gaps that could affect the submission or walkthrough. Finish the
  core workflows and their tests before proposing extra features.

## Before submitting

- [ ] Cross-check the current Moodle assignment and Class 8 materials
      for additional requirements, and confirm the presentation slot.
- [ ] Open the public repo and the deployed URL in a private browser window.
- [ ] Verify that the deployed app corresponds to the code on `main`.
- [ ] Follow the README instructions from a fresh clone and run all tests.
- [ ] Confirm all four names and student numbers, the deployed URL,
      and working local run and test commands are in `README.md`.
- [ ] Confirm all four members have contributed code and rehearse
      explaining a workflow implemented by another member.
- [ ] Test a valid buddy confirmation, a duplicate check-in or
      confirmation, self-confirmation, an action outside a game night,
      a visit after midnight, a tie, and a second minigame attempt at a
      different arena. Verify that rejected actions leave points unchanged.
- [ ] Rehearse the live demo on the deployed app with two demo accounts
      and prepared standings that show a territory changing hands.
- [ ] Check that the public repo contains no credentials or local secrets.
- [ ] Have one member submit the repository link on Moodle by the
      deadline and verify the submission confirmation.

Course source:
https://2477-introduction-programming.gitlab.io/2324_s2/team-project/
