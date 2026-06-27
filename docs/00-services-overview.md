# Services Overview — What Each Service Does

[Home](../setup.md) | [Services Reference →](11-services-reference.md)

---

Your self-hosted stack replaces dozens of paid SaaS products. This guide maps each service to the commercial product it replaces and explains what it offers.

---

## Cloud Storage & Files

| Service | Replaces | What it does |
| --- | --- | --- |
| **Nextcloud** | Google Drive, Dropbox, OneDrive | Full cloud suite — file sync, calendar, contacts, office docs, video calls. The Swiss Army knife of self-hosting. |
| **Syncthing** | Dropbox Sync, Resilio Sync | Peer-to-peer file sync between your devices. No cloud server — files go directly between machines, encrypted. |

## Photos & Media

| Service | Replaces | What it does |
| --- | --- | --- |
| **Immich** | Google Photos, iCloud Photos | Photo and video backup with mobile app. AI-powered face recognition, search, memories, and sharing. Closest Google Photos alternative. |
| **Jellyfin** | Netflix, Plex, Emby | Stream your own movies, TV shows, and music to any device. Free and open source — no subscriptions, no tracking. |
| **Audiobookshelf** | Audible, Spotify (podcasts) | Audiobook and podcast server. Mobile app with offline downloads, bookmarks, and progress sync across devices. |

## Documents & Productivity

| Service | Replaces | What it does |
| --- | --- | --- |
| **Paperless-ngx** | Adobe Scan, Evernote (documents) | Scans, OCRs, and indexes documents. Drop a PDF in and it auto-tags, dates, and makes it full-text searchable. Paperless office. |
| **Stirling PDF Lite** | Adobe Acrobat, Smallpdf, ILovePDF | Merge, split, rotate, compress, convert PDFs. Runs entirely locally — no files uploaded to third parties. |
| **Stirling PDF Full** | Adobe Acrobat Pro | Everything in Lite + OCR + LibreOffice conversions (Word/Excel → PDF). Heavier (~1.5 GB RAM). |
| **Mealie** | Paprika, Whisk, recipe bookmarks | Recipe manager. Paste a URL and it auto-imports the recipe. Meal planning, shopping lists, and family sharing. |

## Code & Git Hosting

| Service | Replaces | What it does |
| --- | --- | --- |
| **Gitea** | GitHub, Bitbucket | Lightweight Git hosting. Repos, issues, pull requests, CI/CD (Actions). Fast and low on resources (~100 MB RAM). |
| **Forgejo** | GitHub, Bitbucket | Community fork of Gitea — same features, fully open governance. Actions runner for CI/CD pipelines. |
| **GitLab CE** | GitHub Enterprise, GitLab.com | Full DevOps platform — repos, CI/CD, container registry, wiki, issue boards. Heavy (~4 GB RAM) but feature-complete. |

## Project Management & Invoicing

| Service | Replaces | What it does |
| --- | --- | --- |
| **OpenProject** | Jira, Asana, Monday.com | Project management with Gantt charts, agile boards, time tracking, and team wikis. Good for structured/waterfall projects. |
| **Plane** | Linear, Jira, Trello | Modern project tracker — cycles, modules, views, and a clean UI. Best for agile/sprint-based teams. |
| **Crater** | FreshBooks, QuickBooks, Zoho Invoice | Invoicing and expense tracking. Create clients, send invoices, track payments. Good for freelancers and small businesses. |

## Email

| Service | Replaces | What it does |
| --- | --- | --- |
| **Stalwart Mail** | Gmail (server), Postfix + Dovecot | All-in-one mail server — SMTP sending, IMAP mailboxes, spam filtering, and web admin. Single container, easy to configure. |
| **Snappymail** | Gmail (web UI), Hey.com | Fast, minimal webmail client. Connects to any IMAP server (including Stalwart). Low resource usage. |
| **Roundcube** | Gmail (web UI), Outlook.com | Full-featured webmail with plugins, address book, and calendar integration. More traditional UI than Snappymail. |

## Communication & Notifications

| Service | Replaces | What it does |
| --- | --- | --- |
| **Conduit (Matrix)** | Slack, Discord, WhatsApp (group chat) | Matrix homeserver for encrypted messaging. Federated — chat with users on other Matrix servers. Use Element as the client app. |
| **Ntfy** | Pushover, Firebase Cloud Messaging | Push notifications to your phone/desktop via simple HTTP POST. Great for alerts from scripts, cron jobs, and monitoring. |
| **Miniflux** | Feedly, Inoreader, Google Reader | Minimal RSS/Atom feed reader. Subscribe to blogs, news sites, YouTube channels. Clean reading experience, no algorithms. |

## Security & Identity

| Service | Replaces | What it does |
| --- | --- | --- |
| **Vaultwarden** | Bitwarden, 1Password, LastPass | Password manager. Full Bitwarden-compatible server — browser extensions, mobile apps, and TOTP all work. |
| **Authentik** | Okta, Auth0, Google Workspace SSO | Single sign-on (SSO) provider. One login for all your services via OAuth2, OIDC, SAML, or LDAP. |

## VPN & Networking

| Service | Replaces | What it does |
| --- | --- | --- |
| **Headscale** | Tailscale (coordination server) | Self-hosted Tailscale control server. Mesh VPN — access your home network from anywhere without port forwarding. |
| **WireGuard (wg-easy)** | NordVPN, ExpressVPN (self-hosted) | Simple VPN tunnel with a web UI. Connect to your home network securely from any device. |
| **OpenVPN** | Commercial VPN services | Traditional VPN server. Broader client compatibility than WireGuard (works on older devices/corporate networks). |
| **Cloudflared** | ngrok, Pagekite | Cloudflare Tunnel — exposes your services to the internet without opening firewall ports. Outbound-only connection. |

## Monitoring & Infrastructure

| Service | Replaces | What it does |
| --- | --- | --- |
| **Uptime Kuma** | Pingdom, UptimeRobot, StatusCake | Monitor uptime of your services. Alerts via ntfy/email/Slack when something goes down. Public status page. |
| **Dozzle** | Papertrail, Datadog (logs) | Real-time Docker container log viewer in the browser. No agents, no storage — just tails live logs. |
| **Portainer CE** | Docker Desktop, Rancher | Web UI to manage Docker containers, images, volumes, and networks. Visual alternative to the command line. |
| **Dockge** | Portainer (compose management) | Docker Compose stack manager with a clean UI. Create, edit, and manage compose files from the browser. |
| **nginx-plain** | Cloudflare Pages, Vercel (routing) | Reverse proxy — routes `service.yourdomain.com` to the right container. Config-file based, domain-templated. |
| **Nginx Proxy Manager** | Cloudflare Pages (with UI) | Same as nginx-plain but with a web UI for managing proxy hosts and SSL certificates. |
| **Landing Page** | Linktree, Homer, Heimdall | Dashboard showing all your services with live health status. Auto-discovers services from your stack. |

---

## Cost Comparison

What you would pay for equivalent commercial services (per year, 1 user):

| Category | Commercial cost (approx.) | Self-hosted cost |
| --- | --- | --- |
| Cloud storage (Google One 2TB) | $100/yr | $0 |
| Photo backup (Google One / iCloud) | $100/yr | $0 |
| Password manager (Bitwarden Premium) | $10/yr | $0 |
| Media streaming (Netflix + Audible) | $300/yr | $0 |
| Git hosting (GitHub Pro) | $48/yr | $0 |
| Project management (Linear/Jira) | $96/yr | $0 |
| VPN (NordVPN) | $60/yr | $0 |
| RSS reader (Feedly Pro) | $72/yr | $0 |
| PDF tools (Adobe Acrobat) | $240/yr | $0 |
| Email (Google Workspace) | $72/yr | $0 |
| Uptime monitoring (UptimeRobot Pro) | $84/yr | $0 |
| SSO (Okta starter) | $240/yr | $0 |
| Invoicing (FreshBooks Lite) | $204/yr | $0 |
| **Total** | **~$1,600/yr** | **$0 + hardware/electricity** |

> Your only costs are the server hardware and electricity. All software is free and open source.

---

[Home](../setup.md) | [Services Reference →](11-services-reference.md)
