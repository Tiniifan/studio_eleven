attribute vec4 atr_pos;
attribute vec4 atr_clr;
attribute vec3 atr_nrm;
attribute vec3 atr_tng;
attribute vec4 atr_tx0;
attribute vec4 atr_tx1;
attribute vec4 atr_tx2;
attribute vec4 atr_pr0;
attribute vec4 atr_pr1;
attribute vec4 atr_pr2;
varying vec4 var_pos;
varying vec4 var_clr;
varying vec4 var_nrm;
varying vec4 var_tng;
varying vec4 var_tx0;
varying vec4 var_tx1;
varying vec4 var_tx2;
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
    vec3 m_nrm;
    vec3 m_tng;
    vec4 m_tx0;
    vec4 m_tx1;
    vec4 m_tx2;
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
    m_nrm = atr_nrm;
    m_tng = atr_tng;
    m_tx0 = atr_tx0;
    m_tx1 = atr_tx1;
    m_tx2 = atr_tx2;
    m_pr0 = atr_pr0;
    m_pr1 = atr_pr1;
    m_pr2 = atr_pr2;
    m_eye_vec = vec3(0.000000, 0.000000, 0.000000);
    m_gen = vec4(0.000000, 0.000000, 0.000000, 0.000000);
    tmp_vec0.x = dot(m_tng.xyz, unf_vtx_lcl_glb[0].xyz);
    tmp_vec0.y = dot(m_tng.xyz, unf_vtx_lcl_glb[1].xyz);
    tmp_vec0.z = dot(m_tng.xyz, unf_vtx_lcl_glb[2].xyz);
    tmp_vec0.w = 0.000000;
    m_tng = normalize(tmp_vec0.xyz);
    tmp_vec0.x = dot(m_nrm.xyz, unf_vtx_lcl_glb[0].xyz);
    tmp_vec0.y = dot(m_nrm.xyz, unf_vtx_lcl_glb[1].xyz);
    tmp_vec0.z = dot(m_nrm.xyz, unf_vtx_lcl_glb[2].xyz);
    tmp_vec0.w = 0.000000;
    m_nrm = normalize(tmp_vec0.xyz);
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
    tmp_vec0.x = dot(m_nrm.xyz, unf_vtx_glb_cmr[0].xyz);
    tmp_vec0.y = dot(m_nrm.xyz, unf_vtx_glb_cmr[1].xyz);
    tmp_vec0.z = dot(m_nrm.xyz, unf_vtx_glb_cmr[2].xyz);
    tmp_vec0.w = 0.000000;
    m_nrm = normalize(tmp_vec0.xyz);
    tmp_vec0.x = dot(m_tng.xyz, unf_vtx_glb_cmr[0].xyz);
    tmp_vec0.y = dot(m_tng.xyz, unf_vtx_glb_cmr[1].xyz);
    tmp_vec0.z = dot(m_tng.xyz, unf_vtx_glb_cmr[2].xyz);
    tmp_vec0.w = 0.000000;
    m_tng = normalize(tmp_vec0.xyz);
    tmp_vec0 = vec4(1.000000, 1.000000, 1.000000, 1.000000);
    m_clr = unf_vtx_clr * m_clr * 0.500000 * tmp_vec0;
    tmp_vec0.x = dot(m_tx0, unf_vtx_txt[0]);
    tmp_vec0.y = dot(m_tx0, unf_vtx_txt[1]);
    tmp_vec0.z = m_tx0.z;
    tmp_vec0.w = 0.000000;
    m_tx0 = tmp_vec0;
    tmp_vec0.x = dot(m_tx1, unf_vtx_txt[2]);
    tmp_vec0.y = dot(m_tx1, unf_vtx_txt[3]);
    tmp_vec0.z = 0.000000;
    tmp_vec0.w = 0.000000;
    m_tx1 = tmp_vec0;
    tmp_vec0.x = dot(m_tx2, unf_vtx_txt[4]);
    tmp_vec0.y = dot(m_tx2, unf_vtx_txt[5]);
    tmp_vec0.z = 0.000000;
    tmp_vec0.w = 0.000000;
    m_tx2 = tmp_vec0;
    tmp_vec1.xyz = m_pos.xyz + m_nrm.xyz;
    tmp_vec1.w = m_pos.w;
    tmp_vec0.x = dot(tmp_vec1, unf_vtx_cmr_prj[0]);
    tmp_vec0.y = dot(tmp_vec1, unf_vtx_cmr_prj[1]);
    tmp_vec0.z = dot(tmp_vec1, unf_vtx_cmr_prj[2]);
    tmp_vec0.w = dot(tmp_vec1, unf_vtx_cmr_prj[3]);
    m_nrm_pos = tmp_vec0;
    tmp_vec0.x = dot(m_pos, unf_vtx_cmr_prj[0]);
    tmp_vec0.y = dot(m_pos, unf_vtx_cmr_prj[1]);
    tmp_vec0.z = dot(m_pos, unf_vtx_cmr_prj[2]);
    tmp_vec0.w = dot(m_pos, unf_vtx_cmr_prj[3]);
    m_pos = tmp_vec0;
    var_pos = m_pos;
    var_clr = m_clr;
    var_nrm.xyz = m_nrm;
    var_nrm.w = 1.000000;
    var_tng.xyz = m_tng;
    var_tng.w = 1.000000;
    var_tx0 = m_tx0;
    var_tx1 = m_tx1;
    var_tx2 = m_tx2;
    var_prm.xyz = m_eye_vec;
    var_prm.w = 0.000000;
    var_gen = m_gen;
    gl_Position = m_pos;
}
