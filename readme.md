🪣 SharePoint Delta Sync via Microsoft Graph API

This Python tool synchronizes files from a SharePoint document library or folder using the Microsoft Graph API.
It supports full sync on first run and incremental sync (delta queries) on subsequent runs.



📦 Key Features
Full and incremental (delta) synchronization

Tracks additions, updates, and deletions

Maintains SharePoint folder structure locally

Uses Azure AD app credentials (no user login required)



⚙️ Requirements
Python 3.8+
Microsoft 365 with SharePoint Online
Azure AD App with Sites.Read.All and Files.Read.All application permissions (admin consented)



🚀 Usage
Install dependencies (requests library).

Configure your tenant, client ID, client secret, site name, and domain.

Run the script to start syncing files.

On subsequent runs, only changed or new files are downloaded automatically.



📁 Output
downloaded_files/ → Local folder containing synced SharePoint files

delta_data/ → Stores delta links for incremental updates



🔄 Delta Sync Overview
The script uses Microsoft Graph’s delta query API to track changes.

Each run fetches only updated or new files since the last execution.
