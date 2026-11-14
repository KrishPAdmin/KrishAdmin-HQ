# Personal Gmail and Calendar

Installed on 2026-11-09. Live Google operations remain pending each user's OAuth consent. No accounts are shared by default. Only the enrolled owner can use one-to-one DMs (updated 2026-11-11); the friend retains shared-channel access only. GitHub remains owner-only, available in the verified owner DM and enrolled main channel; other enrolled users do not gain GitHub access.

`hq_workspace` supports readiness, bounded Gmail search/read, primary-calendar event listing, local email/reply drafts, and proposed event creation/update with optional bounded recurrence. Every send or calendar mutation requires a new, exact `workspace confirm ID DIGEST` DM from that same user. Confirmation is checked against the independently fetched Discord message. User A cannot inspect or confirm user B's proposal. Ambiguous writes are reserved and never automatically resent. No mailbox deletion, invitations, shared calendars, attachments, or unattended recurring email is implemented.

Credentials live under private `state/google/accounts/USER_ID.json` on HQ, outside model containers. The host GitHub service also serves the signed `/workspace` endpoint on its existing private socket. It verifies that the Discord channel is a one-to-one DM whose sole recipient is the requesting enrolled user. No public MCP endpoint is exposed.

## Individual connection

1. Create a Google Cloud Desktop OAuth client, enable **Gmail API** and **Google Calendar API**, and configure the consent screen/test users. Download its client JSON privately to HQ. Do not paste the secret into Discord.
2. Run on HQ:

   `python3 google_connect.py --user DISCORD_USER_ID --client /private/path/client.json`

3. If the browser is on another computer, establish an SSH forward first: `ssh -L 8765:127.0.0.1:8765 krishadmin@192.0.2.180`. Open the displayed Google URL in that user's browser, select their account, and grant consent. The callback binds only to HQ loopback and uses state and PKCE. The operator verifies the displayed email matches the intended Discord user before saving it.
4. In a private bot DM ask “Show my Workspace status”, then “List my unread email” and “Show my calendar tomorrow”. Verify the selected account, read results and time zone before confirming a requested write.

Scopes are Gmail read-only, Gmail send, and calendar events on owned calendars. Local drafts do not require Gmail compose/modify scopes. Read-only mode is the default behavior; Google grants the write scopes so explicit confirmations can execute later. Tokens may need reauthorization if revoked or the OAuth app's testing policy expires consent.

The setup command does not send email or change calendar events. A configured connector without OAuth is not a working account integration. Account replacement requires `--replace`; revoking access in Google stops future requests. To disconnect locally, the operator can move that user's private account file out of the active directory and revoke the app grant.

References: [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), [Calendar scopes](https://developers.google.com/workspace/calendar/api/auth), [Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app).
