# Security

Do not include Discord tokens, Spotify credentials, browser cookies, generated `.env` files, or
runtime logs in issues or commits. Report security issues privately to the repository owner.

Runtime secrets belong in the ignored `.env` file or an equivalent secret provider. The YouTube
subscription cookie must use Netscape cookie-file format and remain at the ignored path configured
by `YTDLP_COOKIE_FILE`.

If a secret is exposed, replace it at its issuing service and redeploy the container. Removing a
value from the latest commit does not remove it from Git history.
