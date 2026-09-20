attribute vec4 atr_pos;
varying vec4 var_pos;
varying vec4 var_clr;
uniform vec4 unf_vtx_clr;

void main() {
    var_clr = unf_vtx_clr * 0.500000;
    var_pos = atr_pos;
    gl_Position = atr_pos;
}
