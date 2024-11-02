using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace StudioElevenLib.Level5.Animation
{
    public class AnimationSupport
    {
        [StructLayout(LayoutKind.Sequential, Pack = 1)]
        public struct Header
        {
            public long Magic;
            public int DecompSize;
            public int NameOffset;
            public int CompDataOffset;
            public int Track1Count;
            public int Track2Count;
            public int Track3Count;
            public int Track4Count;
        }

        [StructLayout(LayoutKind.Sequential, Pack = 1)]
        public struct Header2
        {
            public long Magic;
            public long EmptyBlock;
            public int DecompSize;
            public int NameOffset;
            public int CompDataOffset;
            public int Track1Count;
            public int Track2Count;
        }

        [StructLayout(LayoutKind.Sequential, Pack = 1)]
        public struct DataHeader
        {
            public int HashOffset;
            public int TrackOffset;
            public int DataOffset;
        }

        [StructLayout(LayoutKind.Sequential, Pack = 1)]
        public struct Track
        {
            public byte Type;
            public byte DataType;
            public byte Unk;
            public byte DataCount;
            public short Start;
            public short End;
        }

        public struct TableHeader
        {
            public int NodeOffset;
            public int KeyFrameOffset;
            public int DifferentKeyFrameOffset;
            public int DataOffset;
            public int EmptyValue;
        }

        [StructLayout(LayoutKind.Sequential, Pack = 1)]
        public struct Node
        {
            public int BoneNameHash;
            public byte NodeType;
            public byte DataType;
            public byte IsInMainTrack;
            public byte Unk2;
            public int FrameStart;
            public int FrameEnd;
            public int DataCount;
            public int DifferentFrameCount;
            public int DataByteSize;
            public int DataVectorSize;
            public int DataVectorLength;
            public int DifferentFrameLength;
            public int FrameLength;
            public int DataLength;
        }

        public static Dictionary<int, string> TrackType = new Dictionary<int, string>
        {
            {0, "None" },
            {1, "BoneLocation" },
            {2, "BoneRotation" },
            {3, "BoneScale" },
            {4, "UVMove" },
            {5, "UVScale" },
            {6, "UVRotation" },
            {7, "TextureBrightness" },
            {8, "TextureUnk" },
            {9, "Unk" },
        };

        public static Dictionary<string, int> TrackDataCount = new Dictionary<string, int>
        {
            {"BoneLocation", 3 },
            {"BoneRotation", 4 },
            {"BoneScale", 3 },
            {"UVMove", 2 },
            {"UVScale", 2 },
            {"UVRotation", 1 },
            {"TextureBrightness", 1 },
            {"TextureUnk", 3 },
            {"Unk", 1 },
        };

        public static Dictionary<string, int> TrackDataType = new Dictionary<string, int>
        {
            {"BoneLocation", 2 },
            {"BoneRotation", 2 },
            {"BoneScale", 2 },
            {"UVMove", 2 },
            {"UVScale", 2 },
            {"UVRotation", 3 },
            {"TextureBrightness", 2 },
            {"TextureUnk", 2 },
            {"Unk", 4 },
        };

        public static Dictionary<string, int> TrackDataSize = new Dictionary<string, int>
        {
            {"BoneLocation", 4 },
            {"BoneRotation", 4 },
            {"BoneScale", 4 },
            {"UVMove", 4 },
            {"UVScale", 4 },
            {"UVRotation", 4 },
            {"TextureBrightness", 4 },
            {"TextureUnk", 4 },
            {"Unk", 1 },
        };
    }
}
