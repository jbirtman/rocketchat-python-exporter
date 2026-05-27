# rocketchat-python-exporter
A simple python script that iterates through all of your rocketchat rooms (groups, direct messages, and channels) and exports all of the conversations and attachements. It produces a useful index.html, which then lets you access all of these offline and easily readable. 

## Quickstart
1. Download the rocketchat-export.py script.
2. Edit the variables on line 19, 20, and 21.
```
RC_SERVER = "https://chat.example.com"
RC_AUTH_TOKEN = "PASTE_YOUR_TOKEN_HERE"
RC_USER_ID = "PASTE_YOUR_ROCKETCHAT_USER_ID_HERE"
```
4. Run ```python rocketchat-export.py```
