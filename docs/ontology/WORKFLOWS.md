# Workflows

## Check in and score

Updated direction: automatic location verification replaces buddy confirmation.

1. Player opens Check in and selects a configured drink type and size.
2. Player takes a required photo. Recommended: request current phone location
   at capture time; inspect photo coordinates if present as supporting evidence.
3. App shows the detected territory and scoring preview: base points,
   ownership reduction if applicable, and estimated awarded points.
4. Player submits. Server validates required inputs, location evidence,
   eligibility and duplicate protection using agreed rules.
5. If accepted, server saves the check-in and calculated points and updates
   territory standings/ownership consistently. The app shows points awarded
   and any ownership change, with links to Map and Standings.
6. If rejected, no points change. Explain why and offer a relevant retry.
   If the network result is uncertain, retrieve the submission status before
   retrying; do not create a second award.

The preview is an estimate until accepted: another player may change
ownership before submission. Exact modifier timing needs team agreement.
Photo/location failures must never be represented as a successful check-in.
