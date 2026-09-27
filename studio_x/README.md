# Studio X

## 💡 About
Studio X is a Blender addon designed to import Unity files (models, textures, animations, and cameras) and prepare them for export with [Studio Eleven](https://github.com/Tiniifan/studio_eleven). 

While it primarily targets **Inazuma Eleven Cross**, it may also be able to open Unity assets from other games, though this is not officially supported or guaranteed.

## ⚠️ Compatibility
- **Requires:** the Studio Eleven addon, installed and enabled
- **Minimum Blender version:** 2.8
- **Maximum Blender version:** 3.4
- **Important:** The addon may not function properly on Blender versions beyond 3.4

## 📂 Supported Content
The addon imports the following content from Unity bundles and `.assets` files:

- **Models** - Meshes and armatures
- **Textures** - Adapted to a single texture per material
- **Bone animations**
- **UV animations**
- **Material animations** - Transparency
- **Cameras** - Converted to Studio Eleven cameras

## 🛠️ Installation

1. Install and enable [Studio Eleven](https://github.com/Tiniifan/studio_eleven/releases/latest)
2. Zip the `studio_x` folder (or download the `.zip` of the addon)
3. Open Blender and navigate to **Edit** → **Preferences** → **Add-ons**
4. Click **Install** and select the `.zip` file
5. Enable the addon by checking the checkbox next to "Studio X"

## 🚀 Usage

1. Open **File** → **Import** → **Studio X (Unity bundle / assets)** and select one or several files. If a model uses files from another bundle, select both bundles together
2. Choose the options in the side panel, for example:
   - **Platform**: `3DS` to adapt the cameras and the frame rate to the 3DS screen
   - **Split Camera**: one camera per shot of the move
   - **Use 3DS Bodies and Ball**: replaces the Unity players and ball by the 3DS ones, with the same animation
   - **Reduce 512 Textures** (on by default): every texture 512 pixels wide or high is halved on both sides (512x512 becomes 256x256, 512x256 becomes 256x128), lighter for the 3DS
   - **Waza Name**: the name of the 3DS move (for example `whs0001`), so the exported files get the names used by the game
3. A window lists the players, the ball, the effects and the cameras found in the files. Uncheck what you don't want, then click **OK**
4. Export the scene with Studio Eleven: **File** → **Export** → **.xc**

Your options are remembered for the next import.

To reduce the number of faces of the imported models, use the **Studio Optimizer** addon.

## 🙏 Special Thanks

This project was made possible thanks to the following projects:

- **[UnityPy](https://github.com/K0lb3/UnityPy)** - Unity file formats
- **[AssetStudioMod](https://github.com/aelurum/AssetStudioMod)** - Unity animations and meshes
- **[AssetRipper](https://github.com/AssetRipper/AssetRipper)** - Unity animations and materials
- **[UABEANext](https://github.com/nesrak1/UABEANext)** - Unity file analysis

## 📄 License

This project is open-source and available under the terms specified in the repository license.
