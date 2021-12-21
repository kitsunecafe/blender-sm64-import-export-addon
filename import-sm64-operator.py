
# We're gonna hack the fuck out of this source.
# In order to avoid the complexity of
# implementing a C++ AST, we''re going to
# abuse regex and do some C++ parsing with
# regex.

import re
import tempfile
import bpy
import os
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty, EnumProperty
from bpy.types import Operator

bl_info = {
    "name": "Import SM64 Model",
    "blender": (2, 80, 0),
    "category": "Import-Export",
}

ply_template = """ply
format ascii 1.0
element vertex {vertex_count}
property float x
property float y
property float z
property float nx
property float s
property float t
property uchar red
property uchar green
property uchar blue
property uchar alpha
element face {face_count}
property list uchar uint vertex_indices
end_header
{vertices}
{faces}
"""

# Helper function for a functional pipe
# (value, fn1, fn2, ...) -> output
def pipe(first, *args):
    for fn in args:
        first = fn(first)
    return first


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


class Polygon:
    def __init__(self):
        return


class VertexData:
    def __init__(self, position, normal, uv, rgba):
        self.position = position
        self.normal = normal
        self.uv = uv
        self.rgba = rgba

    def __repr__(self):
        return f"{' '.join(self.position)} {self.normal} {' '.join(self.uv)} {' '.join(self.rgba)}"


class VertexGroup:
    # values gets passed in as a list of lists
    # [
    #		[x, y, y, normal, uvx, uvy, r, g, b, a],
    #		...
    # ]
    def __init__(self, name, values, convert_z):
        self.name = name
        self.vertices = []
        for value in values:
            position = self.to_z_up(value[:3]) if convert_z else value[:3]
            normal = value[4]
            uv = [str(int(n, 0) / 1024) for n in value[4:6]]
            rgba = [str(int(n, 0)) for n in value[6:]]
            self.vertices.append(VertexData(position, normal, uv, rgba))

    def __repr__(self):
        faces = [f"3 {' '.join(f)}" for f in self.faces]
        face_count = len(faces)
        return ply_template.format(
            vertex_count=len(self.vertices),
            face_count=face_count,
            vertices='\n'.join([str(v) for v in self.vertices]),
            faces='\n'.join(faces)
        )

    def set_faces(self, faces):
        self.faces = faces

    def to_z_up(self, pos):
        return [
            pos[0],
            pos[2],
            pos[1]
        ]


def remove_comments(string):
    pattern = r"(\".*?\"|\'.*?\')|(/\*.*?\*/|//[^\r\n]*$)"
    regex = re.compile(pattern, re.MULTILINE | re.DOTALL)

    def _replacer(match):
        if match.group(2) is not None:
            return ""
        else:
            return match.group(1)
    return regex.sub(_replacer, string)


def remove_extra_spaces(string):
    return re.sub(" {2,}", " ", string)


def remove_newlines(string):
    return re.sub("\n", "", string)


def append_newline(string):
    return string + '\n'


def strip_whitespace(string):
    return string.strip()


def find_all_verts(string, convert_z):
    regex = r"(static const Vtx (\w+)+\[\] = {(.+?)};)"
    vert_data = re.finditer(regex, string)
    verts = {}
    for data in vert_data:
        name = data[2]
        vert_data = re.findall("((?:-?\w+)+),?", data[3])
        values = chunks(vert_data, 10)
        verts[name] = VertexGroup(name, values, convert_z)
    return verts


def find_all_faces(verts, string):
    regex = r"(static const Gfx (\w+)+\[\] = {(.+?)};)"
    gfx_data = re.finditer(regex, string)
    for gfx in gfx_data:
        name = gfx[2]
        fns = re.finditer("(gsSPVertex.+?)(?=gsSPVertex|$)", gfx[3])
        for faces in fns:
            [(vert_name, face_data)] = re.findall(
                "gsSPVertex\((\w+).+?\),(.+)", faces[0])
            face_values = re.findall("(?<!\w)(\d+),", face_data)
            tris = chunks(face_values, 3)
            verts[vert_name].set_faces(tris)

    return verts.values()


def read_some_data(context, filepath, convert_z):
    f = open(filepath, "r")

    content = pipe(
        f.read(),
        remove_comments,
        remove_newlines,
        remove_extra_spaces
    )

    f.close()

    verts = find_all_verts(content, convert_z)
    tris = find_all_faces(verts, content)

    for tri in tris:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".ply",
            mode='wb',
            delete=False
        )

        try:
            ply_content = pipe(
                str(tri),
                append_newline,
                strip_whitespace,
                str.encode
            )

            tmp.write(ply_content)
            tmp.close()

            link_path = os.path.join(tempfile.gettempdir(), f"{tri.name}.ply")
            os.link(tmp.name, link_path)

            try:
                bpy.ops.import_mesh.ply(filepath=link_path)
#                bpy.context.scene.objects[tmp.name]
            finally:
                os.unlink(link_path)

        finally:
            os.unlink(tmp.name)

    return {'FINISHED'}


# ImportHelper is a helper class, defines filename and
# invoke() function which calls the file selector.
class ImportSM64Model(Operator, ImportHelper):
    """This appears in the tooltip of the operator and in the generated docs"""
    bl_idname = "import_test.some_data"  # important since its how bpy.ops.import_test.some_data is constructed
    bl_label = "Import SM64 Model"

    # ImportHelper mixin class uses this
    filename_ext = ".inc.c"

    filter_glob: StringProperty(
        default="*.inc.c",
        options={'HIDDEN'},
        maxlen=255,  # Max internal buffer length, longer would be clamped.
    )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling.
    convert_z: BoolProperty(
        name="Convert to Z-up",
        description="Select if the model is Y-up",
        default=True,
    )

    # type: EnumProperty(
    #     name="Example Enum",
    #     description="Choose between two items",
    #     items=(
    #         ('OPT_A', "First Option", "Description one"),
    #         ('OPT_B', "Second Option", "Description two"),
    #     ),
    #     default='OPT_A',
    # )

    def execute(self, context):
        return read_some_data(context, self.filepath, self.convert_z)


# Only needed if you want to add into a dynamic menu
def menu_func_import(self, context):
    self.layout.operator(ImportSM64Model.bl_idname, text="Import SM64 Model")


def register():
    bpy.utils.register_class(ImportSM64Model)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.utils.unregister_class(ImportSM64Model)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)


if __name__ == "__main__":
    register()

    # test call
    bpy.ops.import_test.some_data('INVOKE_DEFAULT')

