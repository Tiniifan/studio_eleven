attribute vec4 atr_pos;
attribute vec4 atr_clr;
attribute vec4 atr_pr0;
attribute vec4 atr_pr1;
attribute vec4 atr_pr2;
varying vec4 var_pos;
varying vec4 var_clr;
varying vec4 var_prm;
varying vec4 var_gen;
uniform vec4 unf_vtx_cmr_prj[4];
uniform vec4 unf_vtx_glb_cmr[3];
uniform vec4 unf_vtx_lcl_glb[3];
uniform vec4 unf_vtx_eye;
uniform vec4 unf_vtx_txt[6];
uniform vec4 unf_vtx_str;
uniform vec4 unf_vtx_clr;

vec3 lxpReflect(const in vec3 in_v0, const in vec3 in_nrm) {
    return 2.000000 * dot(in_v0, in_nrm) * in_nrm - in_v0;
}

vec3 lxpRefract(const in vec3 in_v0, const in vec3 in_nrm, const in float in_r) {
    return -in_r * dot(in_v0, in_nrm) * in_nrm - in_v0;
}

vec3 lxpRefractEx(const in vec3 in_v0, const in vec3 in_nrm, const in float in_r) {
    float rad;
    rad = dot(in_v0, in_nrm);
    if (0 <= rad) {
        return lxpRefract(in_v0, in_nrm, in_r);
    } else {
        return lxpRefract(in_v0, -in_nrm, -in_r);
    }
}

void main() {
    vec4 m_pos;
    vec4 m_clr;
    vec4 m_pr0;
    vec4 m_pr1;
    vec4 m_pr2;
    vec3 m_eye_vec;
    vec4 m_gen;
    vec4 m_nrm_pos;
    vec4 tmp_vec0;
    vec4 tmp_vec1;
    vec4 tmp_vec2;
    vec4 tmp_vec3;
    m_pos = atr_pos;
    m_clr = atr_clr;
    m_pr0 = atr_pr0;
    m_pr1 = atr_pr1;
    m_pr2 = atr_pr2;
    m_eye_vec = vec3(0.000000, 0.000000, 0.000000);
    m_gen = vec4(0.000000, 0.000000, 0.000000, 0.000000);
    tmp_vec0.x = dot(m_pos.xyz, unf_vtx_lcl_glb[0].xyz) + unf_vtx_lcl_glb[0].w;
    tmp_vec0.y = dot(m_pos.xyz, unf_vtx_lcl_glb[1].xyz) + unf_vtx_lcl_glb[1].w;
    tmp_vec0.z = dot(m_pos.xyz, unf_vtx_lcl_glb[2].xyz) + unf_vtx_lcl_glb[2].w;
    tmp_vec0.w = 1.000000;
    m_pos = tmp_vec0;
    tmp_vec0.x = dot(m_pos.xyz, unf_vtx_glb_cmr[0].xyz) + unf_vtx_glb_cmr[0].w;
    tmp_vec0.y = dot(m_pos.xyz, unf_vtx_glb_cmr[1].xyz) + unf_vtx_glb_cmr[1].w;
    tmp_vec0.z = dot(m_pos.xyz, unf_vtx_glb_cmr[2].xyz) + unf_vtx_glb_cmr[2].w;
    tmp_vec0.w = 1.000000;
    m_pos = tmp_vec0;
    m_eye_vec = m_pos.xyz;
    tmp_vec0 = vec4(1.000000, 1.000000, 1.000000, 1.000000);
    m_clr = unf_vtx_clr * m_clr * 0.500000 * tmp_vec0;
    tmp_vec0.x = dot(m_pos, unf_vtx_cmr_prj[0]);
    tmp_vec0.y = dot(m_pos, unf_vtx_cmr_prj[1]);
    tmp_vec0.z = dot(m_pos, unf_vtx_cmr_prj[2]);
    tmp_vec0.w = dot(m_pos, unf_vtx_cmr_prj[3]);
    m_pos = tmp_vec0;
    var_pos = m_pos;
    var_clr = m_clr;
    var_prm.xyz = m_eye_vec;
    var_prm.w = 0.000000;
    var_gen = m_gen;
    gl_Position = m_pos;
}
