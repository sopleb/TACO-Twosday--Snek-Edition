#version 330

layout(location = 0) in vec2 position;
layout(location = 1) in vec2 texCoord;
layout(location = 2) in vec4 color;

uniform mat4 projection;

out vec2 vTexCoord;
out vec4 vColor;

void main()
{
    vTexCoord = texCoord;
    vColor = color;
    gl_Position = projection * vec4(position, 0.0, 1.0);
}
