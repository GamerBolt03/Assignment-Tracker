# Assignment Tracker

A simple application that automatically keeps track of assignments and tasks sent through Gmail.

I originally built this because I kept forgetting assignments after reading the email once. Instead of constantly checking my inbox or trying to remember everything, this app scans incoming emails, finds assignment-related messages, and keeps everything in one place.

It supports multiple Gmail accounts, making it useful for both school and work.

---

## Features

- Monitors Gmail for new assignments
- Automatically keeps track of tasks found in emails
- Supports multiple Gmail accounts
- Clean and simple interface
- Available as a web application
- Can also be downloaded as a Windows executable

---

## Why I Made It

I have a habit of reading an email, thinking I'll remember it later... and then completely forgetting about it.

This project started as a way to solve that problem for myself. Instead of relying on memory, the app keeps a running list of assignments so I always know what needs to be done.

---

## Roadmap

- [x] Gmail integration
- [x] Assignment tracking
- [x] Multiple account support
- [x] Web application
- [x] Windows executable
- [ ] Better assignment detection
- [ ] Due date reminders
- [ ] Calendar integration
- [ ] Mobile support

---

## Installation

### Run from Source

```bash
git clone https://github.com/GamerBolt03/Assignment-Tracker.git
cd Assignment-Tracker
```

Install the required packages:

```bash
pip install -r requirements.txt
```

Start the application:

```bash
python app.py
```

### Executable

Download the latest release from the Releases page and run the installer.

---

## Technologies Used

- Python
- Gmail API
- HTML / CSS / JavaScript
- Flask
- SQLite

---

## Contributing

Suggestions, bug reports, and pull requests are welcome. If you find an issue or have an idea that could improve the project, feel free to open one.
