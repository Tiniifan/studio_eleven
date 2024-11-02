from struct import pack, unpack, unpack_from, calcsize, Struct
from io import BytesIO
from enum import Enum
from zlib import crc32
from ..compression import *
from ..animation import *
from . import animationsupport

def ReadString(byte_io):
    bytes_list = []
    while True:
        byte = byte_io.read(1)
        if byte == b'\x00':
            break
        bytes_list.append(byte)
    name = b''.join(bytes_list).decode('shift-jis')
    return name

class Frame:
    def __init__(self, key: int, value: object=None):
        self.Key = key
        self.Value = value if value else object

class Node:
    def __init__(self, name: int, isMainTrack: bool, Frames: list[Frame]=None):
        self.Name = name
        self.isMainTrack = isMainTrack
        self.Frames = Frames if Frames else []

class Track:
    def __init__(self, name: str, index: int=None, nodes: list[Node]=None):
        self.Name = name
        self.Index = index if index is not None else -1
        self.Nodes = nodes if nodes else []
    
    def GetNodeByName(self, name: int):
        for nodeEntry in self.Nodes:
            if nodeEntry.Name == name:
                return nodeEntry
        return None
    
    def NodeExists(self, name: int) -> bool:
        for nodeEntry in self.Nodes:
            if nodeEntry.Name == name:
                return True
        return False

class AnimationManager:
    def __init__(self, Format=None, Version=None, AnimationName=None, FrameCount=None, Tracks=None,
            reader=None):
        self.Format = Format
        self.Version = Version
        self.AnimationName = AnimationName
        self.FrameCount = FrameCount
        self.Tracks: list[Track] = Tracks if Tracks else []
        if reader:
            self.Read(reader)
    
    def Read(self, reader):
        # Read header
        header = animationsupport.Header.Unpack(reader)
        # Get format name
        self.Format = header.Magic.decode()
        # Wrong header? Try the second pattern
        if header.DecompSize == 0:
            reader.seek(0)
            header2 = animationsupport.Header2.Unpack(reader)
            header.DecompSize = header2.DecompSize
            header.NameOffset = header2.NameOffset
            header.CompDataOffset = header2.CompDataOffset
            header.Track1Count = header2.Track1Count
            header.Track2Count = header2.Track2Count
            # Track3 and Track4 doesn't exist in this header
            header.Track3Count = -1
            header.Track4Count = -1
        # Track 9 case
        maxNodeBeforeTrack4 = 0
        if header.NameOffset == 0x28 and header.CompDataOffset == 0x58:
            reader.seek(0x24)
            maxNodeBeforeTrack4 = unpack("<I", reader.read(4))[0]
        # Get animation name
        reader.seek(header.NameOffset)
        animHash = unpack("<I", reader.read(4))[0]
        self.AnimationName = ReadString(reader)
        # Get frame count
        reader.seek(header.CompDataOffset - 4)
        self.FrameCount = unpack("<I", reader.read(4))[0]
        # Get decomp block
        reader = BytesIO(compressor.decompress(reader.read()))
        
        hashOffset = unpack("<I", reader.read(4))[0]
        trackoffset = unpack("<I", reader.read(4))[0]
        reader.seek(0)
        if hashOffset == 0x0c:
            self.Version = "V2"
            self.GetAnimationDataV2(reader, header, maxNodeBeforeTrack4)
        else:
            self.Version = "V1"
            self.GetAnimationDataV1(reader, header)
    
    def CountInTrack(self, searchIndex):
        if any(track.Index == searchIndex for track in self.Tracks):
            return len(next(track for track in self.Tracks if track.Index == searchIndex).Nodes)
        elif len(self.Tracks) > searchIndex and self.Tracks[searchIndex].Index == -1:
            return len(self.Tracks[searchIndex].Nodes)
        else:
            return 0
    
    def Save(self):
        with BytesIO() as writer:
            header = animationsupport.Header(
                str(self.Format).encode(),
                0x00,
                0x24,
                0x54,
                0,
                0,
                0,
                0
            )
            header.Track1Count = self.CountInTrack(0)
            header.Track2Count = self.CountInTrack(1)
            header.Track3Count = self.CountInTrack(2)
            header.Track4Count = self.CountInTrack(3)
            # Don't exceed 40 characters
            if len(self.AnimationName) > 40:
                self.AnimationName = self.AnimationName[:40]
            # Write animation hash
            writer.seek(0x24)
            writer.write(crc32(self.AnimationName.encode("shift-jis")))
            writer.write(self.AnimationName.encode("shift-jis"))
            writer.write(self.FrameCount)
            # Write animation data
            if self.Version == "V1":
                self.SaveAnimationDataV1(writer, header)
            else:
                self.SaveAnimationDataV2(writer, header)
            writer.seek(0x00)
            if self.Format == "XMTM":
                header2 = animationsupport.Header2(
                    str(self.Format).encode("shift-jis"),
                    0x00,
                    header.DecompSize,
                    0x24,
                    0x54,
                    self.CountInTrack(0),
                    self.CountInTrack(1),
                )
                writer.write(header2.Pack())
            else:
                writer.write(header.Pack())
            return writer.getvalue()
    
    def GetAnimationDataV1(self, reader, header):
        trackIndex = 0
        tableOffset = 0
        if header.Track1Count > 0:
            for i in range(header.Track1Count):
                self.ReadFrameDataV1(reader, tableOffset, 0, trackIndex)
            trackIndex += 1
        if header.Track2Count > 0:
            for i in range(header.Track2Count):
                self.ReadFrameDataV1(reader, tableOffset, 1, trackIndex)
            trackIndex += 1
        if header.Track3Count > 0:
            for i in range(header.Track3Count):
                self.ReadFrameDataV1(reader, tableOffset, 2, trackIndex)
            trackIndex += 1
        if header.Track4Count > 0:
            for i in range(header.Track4Count):
                self.ReadFrameDataV1(reader, tableOffset, 3, trackIndex)
            trackIndex += 1
    
    def GetAnimationDataV2(self, reader, header, maxNodeBeforeTrack4):
        dataHeader = animationsupport.DataHeader.Unpack(reader)
        # Get name hashes
        reader.seek(dataHeader.HashOffset)
        elementCount = (dataHeader.TrackOffset - dataHeader.HashOffset) // 4
        nameHashes = [unpack("<I", reader.read(4))[0] for i in range(elementCount)]
        # Name information
        pos = 0
        nameDict = {
            0: nameHashes,
            1: nameHashes,
            2: nameHashes,
            3: nameHashes,
        }
        # Track information
        trackCountList = [
            header.Track1Count,
            header.Track2Count,
            header.Track3Count,
            header.Track4Count,
        ]
        trackCount = (1 if header.Track1Count != -1 else 0) + \
                     (1 if header.Track2Count != -1 else 0) + \
                     (1 if header.Track3Count != -1 else 0) + \
                     (1 if header.Track4Count != -1 else 0)
        tracks = []
        for i in range(trackCount):
            reader.seek(dataHeader.TrackOffset + 2 * i)
            reader.seek(unpack("<H", reader.read(2))[0])
            tracks.append(animationsupport.Track.Unpack(reader))
            if tracks[i].Type != 0:
                self.Tracks.append(Track(animationsupport.TrackType[tracks[i].Type], index=i))
                if i < 3 and trackCountList[i + 1] == 0 and i+1 != 3:
                    if maxNodeBeforeTrack4 < 1:
                        pos += trackCountList[i] * 4
                        for j in range(i + 1, trackCount):
                            nameDict[j] = None
                elif tracks[i].Type == 9 and maxNodeBeforeTrack4 > 0:
                    nameDict[i] = None
                    pos += maxNodeBeforeTrack4 * 4
            if nameDict[i] is None:
                reader.seek(dataHeader.HashOffset + pos)
                nameDict[i] = [unpack("<I", reader.read(4))[0] for j in range(trackCountList[i])]
        offset = 0
        index = 0
        trackIndex = 0
        if header.Track1Count > 0:
            self.ReadFrameDataV2(reader, offset, header.Track1Count, dataHeader.DataOffset, nameDict[0], tracks[0], trackIndex)
            trackIndex += 1
        offset += header.Track1Count
        index += 1
        if header.Track2Count > 0:
            self.ReadFrameDataV2(reader, offset, header.Track2Count, dataHeader.DataOffset, nameDict[1], tracks[1], trackIndex)
            trackIndex += 1
        offset += header.Track2Count
        index += 1
        if header.Track3Count > 0:
            self.ReadFrameDataV2(reader, offset, header.Track3Count, dataHeader.DataOffset, nameDict[2], tracks[2], trackIndex)
            trackIndex += 1
        offset += header.Track3Count
        index += 1
        if header.Track4Count > 0:
            self.ReadFrameDataV2(reader, offset, header.Track4Count, dataHeader.DataOffset, nameDict[3], tracks[3], trackIndex)
    
    def SaveAnimationDataV1(self, writerDecomp, header):
        if self.Tracks == None or len(self.Tracks) == 0:
            return
        with BytesIO() as writer:
            hashCount = self.CountHashes()
            hashCountDistinct = self.GetDistincHashes()
            headerPos = 0
            nodeOffset = hashCount * 20
            for i in range(4):
                if i < len(self.Tracks):
                    track = self.Tracks[i]
                    self.FixNode(track.Nodes, self.FrameCount)
                    if len(track.Nodes) > 0:
                        for node in track.Nodes:
                            nameInt = int(node.Name, 16)
                            dataVectorSize = animationsupport.TrackDataCount[track.Name]
                            dataByteSize = animationsupport.TrackDataSize[track.Name]
                            nodeHeader = animationsupport.Node(
                                nameInt,
                                next((key for key, values in animationsupport.TrackType.items() if value == track.Name), None),
                                animationsupport.TrackDataType[track.Name],
                                int(node.isMainTrack),
                                0,
                                0,
                                self.FrameCount,
                                len(node.Frames),
                                self.FrameCount + 1,
                                dataByteSize,
                                dataVectorSize,
                                dataVectorSize * dataByteSize,
                                (self.FrameCount + 1) * 2,
                                len(node.Frames) * 2,
                                len(node.Frames) * dataVectorSize * dataByteSize
                            )
                            # Write node table
                            writer.seek(nodeOffset)
                            writer.write(nodeHeader.Pack())
                            # Write keyframe table
                            keyFrameOffset = writer.tell()
                            writer.write(b''.join(struct.pack("<H", x) for x in self.FillArray(
                                [x.Key for x in node.Frames], self.FrameCount + 1))) # This was horrible
                            self.WriteAlignment(writer, 4, 0)
                            # Write different keyframe table
                            differentKeyFrameOffset = writer.tell()
                            writer.write(b''.join(struct.pack("<H", frame.Key) for frame in node.Frames))
                            self.WriteAlignment(writer, 4, 0)
                            # Write animation data
                            dataOffset = writer.tell()
                            writer.write(b''.join(frame.Value.ToBytes() for frame in node.Frames))
                            if animationsupport.TrackDataSize[track.Name] != 4:
                                self.WriteAlignment(writer, 4, 0)
                            tableHeader = animationsupport.TableHeader(
                                nodeOffset,
                                keyFrameOffset,
                                differentKeyFrameOffset,
                                dataOffset,
                                0,
                            )
                            # Update offset
                            nodeOffset = writer.tell()
                            # Write header table
                            writer.seek(headerPos)
                            writer.write(tableHeader.Pack())
                            headerPos = writer.tell()
            header.DecompSize = len(writer.getvalue()) * 2
            writerDecomp.write(compress(writer.getvalue()))
    
    def SaveAnimationDataV2(self, writerDecomp, header):
        with BytesIO() as writer:
            hashCount = self.CountHashes()
            hashCountDistinct = self.GetDistincHashes()
            nameHashes = self.GetNameHashes()
            # Write data header
            writer.write(pack("<I", 0x0C))
            writer.write(pack("<I", 0x0C + hashCountDistinct * 4))
            writer.write(pack("<I", (0x0C + hashCountDistinct * 4) + 4 * 10))
            # Write name hash
            if hashCountDistinct > 0:
                for i in nameHashes:
                    writer.write(pack("<I", i))
            # Store position
            trackOffset = writer.tell() + 4 * 2
            trackDataOffset = writer.tell() + 4 * 2
            tableOffset = (0x0C + hashCountDistinct * 4) + 4 * 10
            dataOffset = (0x0C + hashCount * 4) + 4 * 10 + hashCount * 16
            # Loop in tracks
            for i in range(4):
                # Write track offset
                writer.seek(0x0C + hashCountDistinct * 4 + i * 2)
                writer.write(pack("<H", trackOffset))
                trackOffset += 8
                # Set track struct
                track  = animationsupport.Track(0, 0, 0, 0, 0, 0)
                if i < len(self.Tracks):
                    myTrack = self.Tracks[i]
                    if len(myTrack.Nodes) > 0:
                        track.Type = next((key for key, value in animationsupport.TrackType.items() if value == myTrack.Name), None) & 0xFF
                        track.DataType = animationsupport.TrackDataType[myTrack.Name] & 0xFF
                        track.Unk = 0
                        track.DataCount = animationsupport.TrackDataCount[myTrack.Name] & 0xFF
                        track.Start = 0
                        track.End = self.FrameCount & 0xFFFF
                        for node in myTrack.Nodes:
                            # Write table header
                            writer.seek(tableOffset)
                            writer.write(pack("<I", dataOffset))
                            writer.write(pack("<I", dataOffset + 4))
                            tableOffset += 8
                            # Write data
                            writer.seek(dataOffset)
                            writer.write(pack(
                                "<H", nameHashes.index(int(node.Name, 16)) if int(node.Name, 16) in nameHashes else -1) & 0xFFFF)
                            # Frame count
                            if len(node.Frames) < 255:
                                writer.write(pack("<B", len(node.Frames) & 0xFF))
                                writer.write(pack("<B", 0x00))
                            else:
                                lowFrameCount = len(node.Frames) & 0xFF
                                highFrameCount = 32 + (len(node.Frames) >> 8) & 0xFF
                                writer.write(pack("<B", lowFrameCount))
                                writer.write(pack("<B", highFrameCount))
                            # Write frames
                            for x in node.Frames:
                                writer.write(pack("<H", x.Key))
                            self.WriteAlignment(writer, 4, 0)
                            # Keep value offset
                            valueOffset = writer.tell()
                            for frame in node.Frames:
                                writer.write(frame.Value.ToBytes())
                            # Update data offset
                            dataOffset = writer.tell()
                            # Finish to write table header
                            writer.seek(tableOffset)
                            writer.write(pack("<I", valueOffset))
                            writer.write(pack("<I", 0x00))
                            tableOffset += 8
                # Write track data
                writer.seek(trackDataOffset)
                writer.write(track.Pack())
                trackDataOffset += 8
            header.DecompSize = len(writer.getvalue())
            writerDecomp.write(compress(writer.getvalue()))
    
    def ReadFrameDataV1(self, reader, tableOffset, trackNum, trackIndex):
        # Read offset table
        reader.seek(tableOffset)
        tableHeader = animationsupport.TableHeader.Unpack(reader)
        tableOffset = reader.tell()
        # Read node
        reader.seek(tableHeader.NodeOffset)
        node = animationsupport.Node.Unpack(reader)
        # Add the track if it doesn't exist
        if all(t.Index != trackNum for t in self.Tracks) and node.NodeType != 0:
            self.Tracks.append(Track(animationsupport.TrackType[node.NodeType], trackNum))
        # Get data index for frame
        reader.seek(tableHeader.KeyFrameOffset)
        dummy = [unpack("<H", reader.read(2))[0] for i in range(node.DifferentFrameLength // 2)]
        dataIndexes = list(set(dummy))
        # Get different frame index
        reader.seek(tableHeader.DifferentKeyFrameOffset)
        dummy = [unpack("<H", reader.read(2))[0] for i in range(node.FrameLength // 2)]
        differentFrames = list(set(dummy))
        frames = []
        for j in range(len(differentFrames)):
            # Get frame
            frame = differentFrames[j]
            dataIndex = dataIndexes[j]
            # Seek data offset
            reader.seek(tableHeader.DataOffset + j * node.DataVectorSize * node.DataByteSize)
            animData = [None] * node.DataVectorSize
            # Decode animation data
            for k in range(node.DataVectorSize):
                if node.DataType == 1:
                    animData[k] = unpack("<h", reader.read(2))[0] / 0x7FFF
                elif node.DataType == 2:
                    animData[k] = unpack("<f", reader.read(4))[0]
                elif node.DataType == 3:
                    animData[k] = unpack("<f", reader.read(4))[0]
                elif node.DataType == 4:
                    animData[k] = unpack("<b", reader.read(1))[0]
                else:
                    raise Exception(f"Data type: {node.DataType} not implemented")
            frames.append(Frame(frame, self.ConvertAnimDataToObject(animData, node.NodeType)))
        self.Tracks[trackIndex].Nodes.append(Node(node.BoneNameHash, node.IsInMainTrack == 1, frames))
    
    def ReadFrameDataV2(self, reader, offset, count, dataOffset, nameHashes, track, trackIndex):
        for i in range(offset, offset + count):
            isMainTrack = True
            reader.seek(dataOffset + 4 * 4 * i)
            flagOffset = unpack("<I", reader.read(4))[0]
            keyFrameOffset = unpack("<I", reader.read(4))[0]
            keyDataOffset = unpack("<I", reader.read(4))[0]
            reader.seek(flagOffset)
            index = unpack("<H", reader.read(2))[0]
            nameHash = nameHashes[index]
            lowFrameCount = unpack("<B", reader.read(1))[0]
            highFrameCount = unpack("<B", reader.read(1))[0]
            keyFrameCount = 0
            if highFrameCount == 0:
                isMainTrack = False
                keyFrameCount = lowFrameCount
            else:
                highFrameCount -= 32
                keyFrameCount = (highFrameCount << 8) | lowFrameCount
            reader.seek(keyDataOffset)
            frames = []
            for k in range(keyFrameCount):
                temp = reader.tell()
                reader.seek(keyFrameOffset + k * 2)
                frame = unpack("<H", reader.read(2))[0]
                reader.seek(temp)
                animData = [None] * track.DataCount
                for j in range(track.DataCount):
                    if track.DataType == 1:
                        animData[j] = unpack("<h", reader.read(2))[0] / 0x7FFF
                    elif track.DataType == 2:
                        animData[j] = unpack("<f", reader.read(4))[0]
                    elif track.DataType == 3:
                        animData[j] = unpack("<f", reader.read(4))[0]
                    elif track.DataType == 4:
                        animData[j] = unpack("<b", reader.read(1))[0]
                    else:
                        raise Exception(f"Data type: {track.DataType} not implemented")
                frames.append(Frame(frame, self.ConvertAnimDataToObject(animData, track.Type)))
            # Create node
            self.Tracks[trackIndex].Nodes.append(Node(nameHash, isMainTrack, frames))
    
    def ConvertAnimDataToObject(self, animData, Type):
        if Type == 1:
            return BoneLocation(animData[0], animData[1], animData[2])
        elif Type == 2:
            return BoneRotation(animData[0], animData[1], animData[2], animData[3])
        elif Type == 3:
            return BoneScale(animData[0], animData[1], animData[2])
        elif Type == 4:
            return UVMove(animData[0], animData[1])
        elif Type == 5:
            return UVScale(animData[0], animData[1])
        elif Type == 6:
            return UVRotate(animData[0])
        elif Type == 7:
            return Transparency(animData[0])
        elif Type == 8:
            return MaterialAttribute(animData[0], animData[1], animData[2])
        elif Type == 9:
            return BoneBool(animData[0])
        else:
            raise Exception(f"Data Type: {Type} not implemented")
    
    def ValueToByteArray(self, value): # Useless
        return value.ToBytes()
    
    def GetDistincHashes(self):
        hashes = set()
        for track in self.Tracks:
            hashes.update(node.Name for node in track.Nodes)
        return len(hashes)
    
    def CountHashes(self):
        return sum(len(track.Nodes) for track in self.Tracks)
    
    def GetNameHashes(self):
        nameHashes = []
        for track in self.Tracks:
            for node in track.Nodes:
                nameInt = int(node.Name, 16)
                if nameInt not in nameHashes:
                    nameHashes.append(nameInt)
        return nameHashes
    
    def FillArray(self, inputArray: list, size):
        result = [int] * size
        lastIndex = 0
        for i in range(len(inputArray)):
            nextValue = 0
            lastValue = inputArray[i]
            if i != (len(inputArray) - 1):
                nextValue = inputArray[i + 1]
            else:
                nextValue = size
            for j in range(lastValue, nextValue):
                result[j] = lastIndex
            lastIndex += 1
        return result
    
    def FixNode(self, nodes: list[Node], frameCount):
        for node in nodes:
            if node.Frames[-1].Key != frameCount:
                node.Frames.append(Frame(frameCount, node.Frames[-1]).Value)
    
    def WriteAlignment(self, writer, alignment=16, alignment_byte=0x0):
        remainder = writer.tell() % alignment
        if remainder == 0:
            return
        padding = alignment - remainder
        writer.write(bytes([alignment_byte] * padding))

#with open("./000.mtm2", "rb") as reader:
#    anim = AnimationManager(reader=reader)