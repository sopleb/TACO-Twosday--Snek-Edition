#version 330

uniform sampler2D tex;
uniform int useTexture;

in vec2 vTexCoord;
in vec4 vColor;

out vec4 fragColor;

void main()
{
    if (useTexture != 0) {
        float a = texture(tex, vTexCoord).r;
        if (a < 0.01)
            discard;
        fragColor = vec4(vColor.rgb, vColor.a * a);
    } else {
        fragColor = vColor;
    }
}
