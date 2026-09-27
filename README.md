# Studio Collection

## 💡 About
Studio Collection is a collection of open-source Blender addons built around Level-5 3D files.

| Addon | Role | Required |
|---|---|---|
| **[Studio Eleven](studio_eleven)** | The main addon: imports and exports Level-5 Nintendo 3DS files in Blender | ✅ Yes |
| **[Studio Optimizer](studio_optimizer)** | Optimizes your models for the export with Studio Eleven | ❌ No |
| **[Studio X](studio_x)** | Imports the Unity models of Inazuma Eleven Cross and prepares them for Studio Eleven | ❌ No |

### Studio Eleven
Studio Eleven is the heart of the collection. It imports and exports the Level-5 3DS formats (meshes, archives, bone/UV/material animations, cameras, materials, ...) for games like Inazuma Eleven Go, Yo-kai Watch, Professor Layton vs. Phoenix Wright and The Snack World.

➡️ See the [Studio Eleven README](studio_eleven/README.md)

### Studio Optimizer
Studio Optimizer reduces the number of faces of your models and splits the models that use more than 24 bones, so they don't explode in some games. It is **not needed** to use Studio Eleven: install it only if you want to optimize your models before the export.

➡️ See the [Studio Optimizer README](studio_optimizer/README.md)

### Studio X
Studio X imports Unity files (models, textures, animations and cameras) from **Inazuma Eleven Cross** and converts them so they can be exported with Studio Eleven. It requires Studio Eleven to be installed and enabled.

➡️ See the [Studio X README](studio_x/README.md)

## 🪶 Why separate addons?
Studio Optimizer and Studio X are **not part of Studio Eleven**. They are separate addons, on purpose:

- **Studio Eleven stays light**: it only contains what is needed to import and export Level-5 files
- **You only install what you need**: if you don't optimize your models or don't work with Inazuma Eleven Cross, you don't need the other addons
- Studio Optimizer and Studio X **use** Studio Eleven, but Studio Eleven never depends on them

## 📦 Why a single repository?
All the addons live in this single repository to avoid having several repositories to follow. The code, the issues and the releases of every addon are in one place, and each release contains a separate `.zip` for each addon.

## 🛠️ Installation

1. Go to the latest release page: https://github.com/Tiniifan/studio_eleven/releases/latest
2. In the **Assets** section, download the `.zip` of the addons you want:
   - `studio_eleven.zip` — **always required**
   - `studio_optimizer.zip` — optional
   - `studio_x.zip` — optional, requires Studio Eleven
3. Open Blender and navigate to **Edit** → **Preferences** → **Add-ons**
4. Click **Install** (on Blender 4.2 and higher: the **⌄** menu at the top right → **Install from Disk...**) and select the downloaded `.zip` file
   - ⚠️ Do **not** unzip the file, select the `.zip` directly
5. Enable the addon by checking the checkbox next to its name ("Studio Eleven", "Studio Optimizer" or "Studio X")
6. Repeat steps 4 and 5 for each `.zip` you downloaded. Install **Studio Eleven first**, since Studio X needs it

## ⚠️ Compatibility
- **Minimum Blender version:** 2.8
- **Recommended Blender version:** 3.4
- **Important:** The addons were mainly tested on Blender 3.4.

## 🤖 AI Notice
Artificial intelligence was used to help write parts of the code for these addons to speed up development on heavy features. However:

- All project logic and architecture are carefully designed beforehand
- AI usage does not affect code quality: addons are thoroughly tested and designed to remain fully intuitive
- All external code and libraries used have been credited

## 📄 License
This project is open-source and available under the terms of the [MIT License](LICENSE).
