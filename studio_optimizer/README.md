# Studio Optimizer

## 💡 About
Studio Optimizer is a Blender addon that gets your models ready for [Studio Eleven](https://github.com/Tiniifan/studio_eleven) and the Level-5 Nintendo 3DS games. In one click it:

- **Reduces the number of faces** of your models, so they run better on the 3DS
- **Splits the models that use more than 24 bones**, since past this limit the model can explode in some games (Yo-Kai Watch 1, 2, 3, Blasters, Snack World)

Your animations keep working after the optimization.

## ⚠️ Compatibility
- **Minimum Blender version:** 2.8
- **Maximum Blender version:** 3.4
- **Important:** The addon may not function properly on Blender versions beyond 3.4

## 🛠️ Installation

1. Zip the `studio_optimizer` folder (or download the `.zip` of the addon)
2. Open Blender and navigate to **Edit** → **Preferences** → **Add-ons**
3. Click **Install** and select the `.zip` file
4. Enable the addon by checking the checkbox next to "Studio Optimizer"

## 🚀 Usage

1. In Object Mode, select the models to optimize
2. In the 3D View, open **Object** → **Optimize the model for studio_eleven**
3. Choose the options, then click **OK**:
   - **Reduce Faces**: simplifies the models. Raise **Max Error** to remove more faces
   - **Split Meshes Over 24 Bones**: cuts the models that use too many bones into several parts (`Body`, `Body_1`, `Body_2`...)

A message at the bottom of Blender tells how many faces were removed and how many models were split.

## 🙏 Special Thanks

This project was made possible thanks to the following work:

- **[meshoptimizer](https://github.com/zeux/meshoptimizer)** - Mesh simplification rules
- **Michael Garland & Paul S. Heckbert** - *Surface Simplification Using Quadric Error Metrics* (1997)
- **[F. Paanakker](https://www.gamedeveloper.com/programming/skinned-mesh-export-optimization)** - Skinned mesh splitting

## 📄 License

This project is open-source and available under the terms specified in the repository license.
