# X (Twitter) source: the three keys

The news bot reads ONE private X List through your own logged-in session
(`src/newsbot/sources/x_cookies.py`, twscrape). No API key exists for this;
the two cookies below are your login. They are as sensitive as your
password: anyone holding them is you on x.com. This is an unofficial client
against X's terms of service, approved by you on 2026-10-25 with that risk
understood; the bot sends one request every 50 s against the List and
nothing else, so the account looks like a person reading a List.

## 1. The two cookies

1. In a desktop browser, log in at https://x.com.
2. Open dev tools (F12 or Cmd-Option-I) -> **Application** tab (Chrome) /
   **Storage** (Firefox) -> **Cookies** -> `https://x.com`.
3. Copy the **Value** of `auth_token` (40 hex chars) and of `ct0` (a long
   hex string). Do not paste them into chat, a commit or a ticket.

Logging out of x.com in that browser invalidates `auth_token`; stay logged
in, or mint them from a browser profile you keep for the bot. If the bot
logs `[news-x] source-error=auth: ...`, repeat this step and redeploy.

## 2. The List

1. On x.com: Lists -> **New List**. Name it anything, tick **Private**.
2. Add the flash accounts (DeItaone, FirstSquawk, WuBlockchain, unusual_whales,
   whoever you want the judge to read).
3. Open the List. The URL is `https://x.com/i/lists/<digits>`; the digits
   are `X_LIST_ID` (the full URL is accepted as well).

## 3. The deployment secret

Add these three keys where the bot's other secrets live (the GitHub
environment / `.env` the `Deploy` workflow writes), then push or redeploy:

```
X_AUTH_TOKEN=<auth_token cookie value>
X_CT0=<ct0 cookie value>
X_LIST_ID=<digits from the List URL>
```

Optional: `X_POLL_S=50` (floor 30), `X_DOMAINS=politics,geo,crypto,corp`
(applied to every tweet from the List), `X_ACCOUNTS_DB` (twscrape's
accounts db; default `data/news/x-accounts.db`, the only place the cookies
are stored).

The source starts only when all three keys are set; the first log line is
`[news-x] polling list=<id> every 50s`.
