from struct import pack, unpack, unpack_from, calcsize, Struct
from io import BytesIO
from enum import Enum

class Header:
    STRCT = Struct("<8s IIIIIII")
    def __init__(self, Magic, DecompSize, NameOffset, CompDataOffset,
            Track1Count, Track2Count, Track3Count, Track4Count):
        self.Magic = Magic
        self.DecompSize = DecompSize
        self.NameOffset = NameOffset
        self.CompDataOffset = CompDataOffset
        self.Track1Count = Track1Count
        self.Track2Count = Track2Count
        self.Track3Count = Track3Count
        self.Track4Count = Track4Count
    @classmethod
    def Unpack(cls, data):
        unpackedData = cls.STRCT.unpack_from(
            data.read(cls.STRCT.size)
        )
        return cls(*unpackedData)
    def Pack(self):
        return pack(self.STRCT.format, self.Magic, self.DecompSize, self.NameOffset, self.CompDataOffset,
                self.Track1Count, self.Track2Count, self.Track3Count, self.Track4Count)

class Header2:
    STRCT = Struct("<8sQ IIIII")
    def __init__(self, Magic, EmptyBlock, DecompSize, NameOffset, CompDataOffset,
            Track1Count, Track2Count):
        self.Magic = Magic
        self.EmptyBlock = EmptyBlock
        self.DecompSize = DecompSize
        self.NameOffset = NameOffset
        self.CompDataOffset = CompDataOffset
        self.Track1Count = Track1Count
        self.Track2Count = Track2Count
    @classmethod
    def Unpack(cls, data):
        unpackedData = cls.STRCT.unpack_from(
            data.read(cls.STRCT.size)
        )
        return cls(*unpackedData)
    def Pack(self):
        return pack(self.STRCT.format, self.Magic, self.EmptyBlock, self.DecompSize, self.NameOffset, self.CompDataOffset,
                self.Track1Count, self.Track2Count)

class DataHeader:
    STRCT = Struct("<III")
    def __init__(self, HashOffset, TrackOffset, DataOffset):
        self.HashOffset = HashOffset
        self.TrackOffset = TrackOffset
        self.DataOffset = DataOffset
    @classmethod
    def Unpack(cls, data):
        unpackedData = cls.STRCT.unpack_from(
            data.read(cls.STRCT.size)
        )
        return cls(*unpackedData)
    def Pack(self):
        return pack(self.STRCT.format, self.HashOffset, self.TrackOffset, self.DataOffset)

class Track:
    STRCT = Struct("<BBBB HH")
    def __init__(self, Type, DataType, Unk, DataCount, Start, End):
        self.Type = Type
        self.DataType = DataType
        self.Unk = Unk
        self.DataCount = DataCount
        self.Start = Start
        self.End = End
    @classmethod
    def Unpack(cls, data):
        unpackedData = cls.STRCT.unpack_from(
            data.read(cls.STRCT.size)
        )
        return cls(*unpackedData)
    def Pack(self):
        return pack(self.STRCT.format, self.Type, self.DataType, self.Unk, self.DataCount, self.Start, self.End)

class TableHeader:
    STRCT = Struct("<IIIII")
    def __init__(self, NodeOffset, KeyFrameOffset, DifferentKeyFrameOffset, DataOffset, EmptyValue):
        self.NodeOffset = NodeOffset
        self.KeyFrameOffset = KeyFrameOffset
        self.DifferentKeyFrameOffset = DifferentKeyFrameOffset
        self.DataOffset = DataOffset
        self.EmptyValue = EmptyValue
    @classmethod
    def Unpack(cls, data):
        unpackedData = cls.STRCT.unpack_from(
            data.read(cls.STRCT.size)
        )
        return cls(*unpackedData)
    def Pack(self):
        return pack(self.STRCT.format, self.NodeOffset, self.KeyFrameOffset, self.DifferentKeyFrameOffset, self.DataOffset, self.EmptyValue)

class Node:
    STRCT = Struct("<I BBBB II I I I II I II")
    def __init__(self, BoneNameHash, NodeType, DataType, IsInMainTrack, Unk2,
            FrameStart, FrameEnd, DataCount, DifferentFrameCount,
            DataByteSize, DataVectorSize, DataVectorLength, DifferentFrameLength,
            FrameLength, DataLength):
        self.BoneNameHash = BoneNameHash
        self.NodeType = NodeType
        self.DataType = DataType
        self.IsInMainTrack = IsInMainTrack
        self.Unk2 = Unk2
        self.FrameStart = FrameStart
        self.FrameEnd = FrameEnd
        self.DataCount = DataCount
        self.DifferentFrameCount = DifferentFrameCount
        self.DataByteSize = DataByteSize
        self.DataVectorSize = DataVectorSize
        self.DataVectorLength = DataVectorLength
        self.DifferentFrameLength = DifferentFrameLength
        self.FrameLength = FrameLength
        self.DataLength = DataLength
    @classmethod
    def Unpack(cls, data):
        unpackedData = cls.STRCT.unpack_from(
            data.read(cls.STRCT.size)
        )
        return cls(*unpackedData)
    def Pack(self):
        return pack(self.STRCT.format, self.BoneNameHash, self.NodeType, self.DataType, self.IsInMainTrack, self.Unk2,
            self.FrameStart, self.FrameEnd, self.DataCount, self.DifferentFrameCount,
            self.DataByteSize, self.DataVectorSize, self.DataVectorLength, self.DifferentFrameLength,
            self.FrameLength, self.DataLength)

TrackType = {
    0: "None",
    1: "BoneLocation",
    2: "BoneRotation",
    3: "BoneScale",
    4: "UVMove",
    5: "UVScale",
    6: "UVRotate",
    7: "MaterialTransparency",
    8: "MaterialAttribute",
    9: "BoneBool",
}
TrackDataCount = {
    "BoneLocation": 3,
    "BoneRotation": 4,
    "BoneScale": 3,
    "UVMove": 2,
    "UVScale": 2,
    "UVRotate": 1,
    "MaterialTransparency": 1,
    "MaterialAttribute": 3,
    "BoneBool": 1,
}
TrackDataType = {
    "BoneLocation": 2,
    "BoneRotation": 1,
    "BoneScale": 2,
    "UVMove": 2,
    "UVScale": 2,
    "UVRotate": 3,
    "MaterialTransparency": 2,
    "MaterialAttribute": 2,
    "BoneBool": 4,
}
TrackDataSize = {
    "BoneLocation": 4,
    "BoneRotation": 2,
    "BoneScale": 4,
    "UVMove": 4,
    "UVScale": 4,
    "UVRotate": 4,
    "MaterialTransparency": 4,
    "MaterialAttribute": 4,
    "BoneBool": 1,
}