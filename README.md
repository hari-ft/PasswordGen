# Password Generator

A small Windows desktop password generator built with Python and Tkinter.

## Run on Windows

Copy `dist\PasswordGenerator.exe` to the Windows computer or folder where you want to use it and double-click it. The executable is built for 64-bit Windows and does not require Python to be installed on the computer where it runs.

## Build the executable

To build or rebuild the single-file executable:

1. Install Python 3 from [python.org](https://www.python.org/downloads/windows/) and enable **Add Python to PATH** during setup.
2. Install the build tool: `py -3 -m pip install pyinstaller`.
3. Double-click **Build Executable.bat**.

The executable will be created at `dist\PasswordGenerator.exe`. You can also run the source directly by double-clicking **Start Password Generator.bat**.

## Features

- Set password length from 4 to 256 by typing a number, using the spinbox arrows, or moving the slider.
- Choose uppercase, lowercase, numbers, and symbols independently.
- Customize the exact symbol characters available for generation. Spaces are ignored.
- Optionally avoid look-alike characters (I, l, 1, O, 0, o).
- Guarantees at least one character from each selected type.
- A new password appears as soon as you open the app or change a setting, with a strength meter showing the estimated entropy in bits.
- Copy the generated password or a selected recent password. The clipboard is cleared automatically after 30 seconds, and when the app closes.
- Hide passwords on screen with the **Hide passwords** option.
- Add an optional note to a password; notes appear beside passwords in the recent list, along with the time.
- View up to 20 recent passwords. A password is added to the list when you click **Generate password** or copy it. History and notes are kept in memory only and are cleared when the app closes.
- Light and dark themes that follow your Windows setting.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| Enter | Generate a new password |
| Ctrl+C | Copy the password (or the selected history entry) |
| Ctrl+S | Save settings |
| Delete | Remove the selected history entry |

## Saved settings

Click **Save settings** to keep your length, character types, allowed symbols, look-alike and hide options. They are stored in `%USERPROFILE%\.password_generator_settings.json` and loaded each time the app starts. Delete that file to go back to the defaults. Passwords and notes are never saved.
