# -*- coding: utf-8 -*-
import pmx
import utils

import math

import bpy
import os
import mathutils


class PMXImporter:
    TO_BLE_MATRIX = mathutils.Matrix([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0]])

    def __init__(self):
        self.__pmxFile = None
        self.__targetScene = bpy.context.scene

        self.__armObj = None
        self.__meshObj = None

        self.__vertexTable = None
        self.__vertexGroupTable = None
        self.__textureTable = None

        self.__materialFaceCountTable = None

    @staticmethod
    def flipUV_V(uv):
        u, v = uv
        return [u, 1.0-v]

    def __getMaterialIndexFromFaceIndex(self, face_index):
        count = 0
        for i, c in enumerate(self.__materialFaceCountTable):
            if face_index < count + c:
                return i
            count += c
        raise Exception('invalid face index.')

    ## 必要なオブジェクトを生成し、ターゲットシーンにリンク
    def __createObjects(self):
        pmxModel = self.__pmxFile.model

        mesh = bpy.data.meshes.new(name=pmxModel.name)
        self.__meshObj = bpy.data.objects.new(name='tmp', object_data=mesh)

        arm = bpy.data.armatures.new(name=pmxModel.name)
        self.__armObj = bpy.data.objects.new(name=pmxModel.name, object_data=arm)
        self.__meshObj.parent = self.__armObj

        self.__targetScene.objects.link(self.__meshObj)
        self.__targetScene.objects.link(self.__armObj)

    def __importVertexGroup(self):
        self.__vertexGroupTable = []
        for i in self.__pmxFile.model.bones:
            self.__vertexGroupTable.append(self.__meshObj.vertex_groups.new(name=i.name))

    def __importVertices(self):
        self.__importVertexGroup()

        pmxModel = self.__pmxFile.model
        mesh = self.__meshObj.data

        mesh.vertices.add(count=len(self.__pmxFile.model.vertices))
        for i, pv in enumerate(pmxModel.vertices):
            bv = mesh.vertices[i]

            bv.co = pv.co
            bv.normal = pv.normal

            if isinstance(pv.weight.weights, pmx.BoneWeightSDEF):
                self.__vertexGroupTable[pv.weight.bones[0]].add(index=[i], weight=pv.weight.weights.weight, type='REPLACE')
                self.__vertexGroupTable[pv.weight.bones[1]].add(index=[i], weight=1.0-pv.weight.weights.weight, type='REPLACE')
            elif len(pv.weight.bones) == 1:
                self.__vertexGroupTable[pv.weight.bones[0]].add(index=[i], weight=1.0, type='REPLACE')
            elif len(pv.weight.bones) == 2:
                self.__vertexGroupTable[pv.weight.bones[0]].add(index=[i], weight=pv.weight.weights[0], type='REPLACE')
                self.__vertexGroupTable[pv.weight.bones[1]].add(index=[i], weight=1.0-pv.weight.weights[0], type='REPLACE')
            elif len(pv.weight.bones) == 4:
                self.__vertexGroupTable[pv.weight.bones[0]].add(index=[i], weight=pv.weight.weights[0], type='REPLACE')
                self.__vertexGroupTable[pv.weight.bones[1]].add(index=[i], weight=pv.weight.weights[1], type='REPLACE')
                self.__vertexGroupTable[pv.weight.bones[2]].add(index=[i], weight=pv.weight.weights[2], type='REPLACE')
                self.__vertexGroupTable[pv.weight.bones[3]].add(index=[i], weight=pv.weight.weights[3], type='REPLACE')
            else:
                raise Exception('unkown bone weight type.')

        mesh.transform(self.TO_BLE_MATRIX)

    def __importTextures(self):
        pmxModel = self.__pmxFile.model

        self.__textureTable = []
        for i in pmxModel.textures:
            name = os.path.basename(i.path).split('.')[0]
            tex = bpy.data.textures.new(name=name, type='IMAGE')
            try:
                tex.image = bpy.data.images.load(filepath=i.path)
            except Exception:
                print('WARNING: failed to load %s'%str(i.path))
            self.__textureTable.append(tex)

    def __importBones(self):

        pmxModel = self.__pmxFile.model

        utils.enterEditMode(self.__armObj)
        try:
            editBoneTable = []
            tipBones = []
            self.__boneTable = []
            for i in pmxModel.bones:
                bone = self.__armObj.data.edit_bones.new(name=i.name)
                loc = mathutils.Vector(i.location)
                loc.rotate(self.TO_BLE_MATRIX)
                bone.head = loc
                editBoneTable.append(bone)
                self.__boneTable.append(i.name)

            for b_bone, m_bone in zip(editBoneTable, pmxModel.bones):
                if m_bone.parent != -1:
                    b_bone.parent = editBoneTable[m_bone.parent]

            for b_bone, m_bone in zip(editBoneTable, pmxModel.bones):
                if isinstance(m_bone.displayConnection, int):
                    if m_bone.displayConnection != -1:
                        b_bone.tail = editBoneTable[m_bone.displayConnection].head
                    else:
                        b_bone.tail = b_bone.head
                else:
                    loc = mathutils.Vector(m_bone.displayConnection)
                    loc.rotate(self.TO_BLE_MATRIX)
                    b_bone.tail = b_bone.head + loc

            for b_bone in editBoneTable:
                if b_bone.length  < 0.001:
                    loc = mathutils.Vector([0, 0, 1])
                    b_bone.tail = b_bone.head + loc
                    if len(b_bone.children) == 0:
                        tipBones.append(b_bone.name)

            for b_bone, m_bone in zip(editBoneTable, pmxModel.bones):
                if b_bone.parent is not None and b_bone.parent.tail == b_bone.head:
                    if not m_bone.isMovable:
                        b_bone.use_connect = True

        finally:
            bpy.ops.object.mode_set(mode='OBJECT')

        pose_bones = self.__armObj.pose.bones
        bpy.types.PoseBone.isTipBone = bpy.props.BoolProperty(name='isTipBone', default=False)
        bpy.types.PoseBone.name_j = bpy.props.StringProperty(name='name_j', description='the bone name in japanese.')
        bpy.types.PoseBone.name_e = bpy.props.StringProperty(name='name_e', description='the bone name in english.')
        for i in tipBones:
            b = pose_bones[i]
            b.isTipBone = True
            b.lock_rotation = [True, True, True]
            b.lock_location = [True, True, True]
            b.lock_scale = [True, True, True]
            b.bone.hide = True

        for p_bone in pmxModel.bones:
            b_bone = pose_bones[p_bone.name]
            b_bone.name_j = p_bone.name_orig
            b_bone.name_e = p_bone.name_e
            if not p_bone.isRotatable:
                b_bone.lock_rotation = [True, True, True]
            if not p_bone.isMovable:
                b_bone.lock_location =[True, True, True]

            if p_bone.isIK:
                if p_bone.target != -1:
                    bone = pose_bones[self.__boneTable[p_bone.target]].parent
                    ikConst = bone.constraints.new('IK')
                    ikConst.chain_count = len(p_bone.ik_links)
                    ikConst.target = self.__armObj
                    ikConst.subtarget = p_bone.name
                    for i in p_bone.ik_links:
                        if i.maximumAngle is not None:
                            bone = pose_bones[self.__boneTable[i.target]]
                            bone.use_ik_limit_x = True
                            bone.use_ik_limit_y = True
                            bone.use_ik_limit_z = True
                            bone.ik_max_x = -i.minimumAngle[0]
                            bone.ik_max_y = i.maximumAngle[1]
                            bone.ik_max_z = i.maximumAngle[2]
                            bone.ik_min_x = -i.maximumAngle[0]
                            bone.ik_min_y = i.minimumAngle[1]
                            bone.ik_min_z = i.minimumAngle[2]


    def __importMaterials(self):
        self.__importTextures()
        bpy.types.Material.ambient_color = bpy.props.FloatVectorProperty(name='ambient color')

        pmxModel = self.__pmxFile.model

        self.__materialTable = []
        self.__materialFaceCountTable = []
        for i in pmxModel.materials:
            mat = bpy.data.materials.new(name=i.name)
            mat.diffuse_color = i.diffuse[0:3]
            mat.alpha = i.diffuse[3]
            mat.ambient_color = i.ambient
            mat.specular_color = i.specular[0:3]
            mat.specular_alpha = i.specular[3]
            self.__materialFaceCountTable.append(int(i.vertex_count/3))
            self.__meshObj.data.materials.append(mat)
            if i.texture != -1:
                texture_slot = mat.texture_slots.add()
                texture_slot.texture = self.__textureTable[i.texture]
                texture_slot.texture_coords = 'UV'

    def __importFaces(self):
        pmxModel = self.__pmxFile.model
        mesh = self.__meshObj.data

        mesh.tessfaces.add(len(pmxModel.faces))
        uvLayer = mesh.tessface_uv_textures.new()
        for i, f in enumerate(pmxModel.faces):
            bf = mesh.tessfaces[i]
            bf.vertices_raw = list(f) + [0]
            bf.use_smooth = True
            face_count = 0
            uv = uvLayer.data[i]
            uv.uv1 = self.flipUV_V(pmxModel.vertices[f[0]].uv)
            uv.uv2 = self.flipUV_V(pmxModel.vertices[f[1]].uv)
            uv.uv3 = self.flipUV_V(pmxModel.vertices[f[2]].uv)

            bf.material_index = self.__getMaterialIndexFromFaceIndex(i)

    def __importVertexMorphs(self):
        pmxModel = self.__pmxFile.model

        for morph in filter(lambda x: isinstance(x, pmx.VertexMorph), pmxModel.morphs):
            shapeKey = self.__meshObj.shape_key_add(morph.name)
            for md in morph.data:
                shapeKeyPoint = shapeKey.data[md.vertex]
                offset = mathutils.Vector(md.offset)
                offset.rotate(self.TO_BLE_MATRIX)
                shapeKeyPoint.co = shapeKeyPoint.co + offset


    def execute(self, **args):
        self.__pmxFile = pmx.File()
        self.__pmxFile.load(args['filepath'])

        self.__createObjects()

        self.__importVertices()
        self.__importBones()
        self.__importMaterials()
        self.__importFaces()

        self.__importVertexMorphs()

        self.__meshObj.data.update()


def main():
    importer = PMXImporter()
    #importer.execute(filepath='D:/primary/program files/MMD/MikuMikuDance_v739dot/UserFile/Model/SUPERリアルカ/ruka.pmx')
    importer.execute(filepath='D:/primary/program files/MMD/MikuMikuDance_v739dot/UserFile/Model/Tda式改変テト制服/Tda式改変テト制服.pmx')
    #importer.execute(filepath='F:/mac-tmp/cg/tmp/初音ミクVer2MP2.pmx')
    #importer.execute(filepath='F:/mac-tmp/cg/tmp/zezemiku/zezemiku.pmx')
    return

    if False:
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.scene.objects.active = obj
        obj.select=True
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.separate(type='MATERIAL')

        for i in root.children:
            mesh = i.data
            if len(mesh.polygons) > 0:
                mat_index = mesh.polygons[0].material_index
                mat = mesh.materials[mat_index]
                for k in mesh.materials:
                    mesh.materials.pop(index=0, update_data=True)
                mesh.materials.append(mat)
                for po in mesh.polygons:
                    po.material_index = 0
                i.name = mat.name

        bpy.ops.object.mode_set(mode='OBJECT')

        m.update()