# NkScriptEditor
![Static Badge](https://img.shields.io/badge/DCC-Nuke-yellow?style=flat) 
![Static Badge](https://img.shields.io/badge/Python-grey?style=flat&logo=python&logoSize=auto) 
![Static Badge](https://img.shields.io/badge/Tool-Nuke%20Panel-lightgrey?logo=nuke&logoColor=yellow)
![GitHub Release Date](https://img.shields.io/github/release-date/JorgeHI/NkScriptEditor)

Nk Script Editor it´s a Qt Panels integrated in Nuke to allow TDs to review and fix Nuke scripts easily. This tool can be use to quickly find invalid characters, bad structures o script errors in the nuke files that prevents Nuke from open them. Also it can be used to easily review Nuke nodes before publish them in a library.

# Features
## Main Tab
![image](https://github.com/user-attachments/assets/69614d3d-7a8d-4cb0-b704-9306936ccc31)
The tool allows the loading of nuke scripts from the node graph, pasting the current nodes in the text editor, loading from the root filepath to the Nuke script or selecting manualy a .nk file to load. The text editor will highlight esencial key words in the script like: Node definitions, node names, knobs, user knob definitions, flags,...


### Search Bar

<img src="https://github.com/user-attachments/assets/8af4611e-4518-471e-8328-58ca15d13e52" width="100%" >

The tool have a Search bar that can be open with "Ctrl+f". In this search bar you can search any word in the script or can change the search mode from all to: Node Type, Node Name, Knob or User Knob. Using this modes you will be able to jump from match to match and quickly find the node or knob you are looking for. The search bar also inclus a warning button that will spec the script looking for non ASCII characters that could be invalidad values for UTF-8. This invalid character will be highlighted in red too.

### Debug

![image](https://github.com/user-attachments/assets/7e6ea41c-90a7-4574-96f9-59d9b7e567e4)

Jump bettwen break points ad find the problem in your script quickly like you will debug any python script.

## Preference tab

![image](https://github.com/user-attachments/assets/96d83dd9-88f2-4a81-b9a8-f5bf011b4fbf)

Customize the highlighting and the wrap text mode and save your preference locally.

## Help Tab

![image](https://github.com/user-attachments/assets/270c8752-e07b-45e9-a40e-762f9a7cec5b)

Quick help and links to the tool pages.

# Documentation
WIP

## Installation

1. Copy the `NkScriptEditor` folder and paste it in a folder that it's in your Nuke plugin path. The most common one, inside the `Users/YourUser/.nuke` directory.
2. Open with a text editor the file `menu.py` that lives next to your `NkScriptEditor` folder, or create one if it doesn’t exist.
3. Add this code:
```python
import NkScriptEditor
NkScriptEditor.init()
```
4. Restart Nuke.

# Supported Versions

![Static Badge](https://img.shields.io/badge/Nuke-%3E%3D13.0-yellow?style=flat&logo=nuke&logoColor=yellow&logoSize=auto)
![Static Badge](https://img.shields.io/badge/Nuke%20Licence-Commercial-yellow?logo=Nuke&logoColor=yellow)
![Static Badge](https://img.shields.io/badge/Python-%3E%3D3.6-blue?style=flat&logo=python&logoSize=auto)


# Author

- [Linkedin](https://www.linkedin.com/in/jorgehi-vfx/)

# Version Log

# 0.2.0
- Validation nk script lenguage.
- Compare two nuke scripts.
- Highlight invalid characters in red.
- Preference improvements.

## 0.1.1
- Debug system with break points.
- Preference system for highlight colors.
- Option to change encode for open and save.
- Improve paste system to use clipboard with backup.
- Add Help tab.
- Improve code documentation.
- Support PySide6 and PySide2 -> Support for Nuke 16.0 >=

## 0.1.0 
    First release
