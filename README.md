# rocketchat-python-exporter
A simple python script that iterates through all of your rocketchat rooms (groups, direct messages, and channels) and exports all of the conversations **AND ATTACHMENTS**. It produces a useful index.html, which then lets you access all of these offline and easily readable. 

## Quickstart
1. Download the rocketchat-export.py script.
2. Edit the variables on line 19, 20, and 21.
```
RC_SERVER = "https://chat.example.com"
RC_AUTH_TOKEN = "PASTE_YOUR_TOKEN_HERE"
RC_USER_ID = "PASTE_YOUR_ROCKETCHAT_USER_ID_HERE"
```
4. Run ```python rocketchat-export.py```

## Results:
```index.html```:

<img width="709" height="461" alt="image" src="https://github.com/user-attachments/assets/6ac2a421-2233-4b03-beb6-f9dad4df7bf3" />

Clicking on the 'General' Channel gives a readable html file:

<img width="992" height="958" alt="image" src="https://github.com/user-attachments/assets/029e2ba9-2539-4014-8a11-cde533f4bee4" />

## How to Find My RocketChat User ID and Auth Token:
1. Click Profile Photo (top left)
2. Click Preferences
3. Click Personal Access Tokens (on the left side)
4. Name your token and click "Add" blue button on the right side.
5. In the "Personal Access Token successfully granted" window, save **(a) your token** and **(b) your user id** to use in this script.
