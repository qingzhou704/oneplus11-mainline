// SPDX-License-Identifier: MIT
// Hardware-only GLES pixel check, with idle and context recreation between rounds.
// gcc -O2 -Wall -Wextra gpu-render.c -o gpu-render $(pkg-config --cflags --libs egl glesv2 gbm)
// ./gpu-render [rounds]
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <fcntl.h>
#include <gbm.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "%s failed (EGL=%x GL=%x)\n", \
    #x, eglGetError(), glGetError()); return 1; } } while (0)

int main(int argc, char **argv)
{
    int rounds = argc == 2 ? atoi(argv[1]) : 3;
    CHECK(rounds > 0);
    int fd = open("/dev/dri/renderD128", O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror("open renderD128"); return 1; }
    struct gbm_device *gbm = gbm_create_device(fd);
    CHECK(gbm);
    EGLDisplay dpy = eglGetPlatformDisplay(EGL_PLATFORM_GBM_KHR, gbm, NULL);
    CHECK(eglInitialize(dpy, NULL, NULL));
    CHECK(eglBindAPI(EGL_OPENGL_ES_API));
    EGLint attrs[] = { EGL_SURFACE_TYPE, 0, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE };
    EGLConfig config;
    EGLint count;
    CHECK(eglChooseConfig(dpy, attrs, &config, 1, &count) && count == 1);
    const EGLint ctxattrs[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    const char *sources[] = {
        "attribute vec2 p; varying vec2 uv; void main(){uv=(p+1.0)*0.5;gl_Position=vec4(p,0,1);}",
        "precision highp float; varying vec2 uv; void main(){gl_FragColor=vec4(uv,0.25,1);}" };
    const GLenum types[] = { GL_VERTEX_SHADER, GL_FRAGMENT_SHADER };
    const GLfloat vertices[] = { -1,-1, 3,-1, -1,3 };
    for (int round = 0; round < rounds; round++) {
        EGLContext ctx = eglCreateContext(dpy, config, EGL_NO_CONTEXT, ctxattrs);
        CHECK(ctx != EGL_NO_CONTEXT);
        CHECK(eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx));
        const char *renderer = (const char *)glGetString(GL_RENDERER);
        CHECK(renderer && (strstr(renderer, "FD740") || strstr(renderer, "Adreno (TM) 740")));
        if (!round) printf("renderer=%s\nversion=%s\n", renderer, glGetString(GL_VERSION));
        GLuint program = glCreateProgram();
        for (int i = 0; i < 2; i++) {
            GLuint shader = glCreateShader(types[i]);
            glShaderSource(shader, 1, &sources[i], NULL);
            glCompileShader(shader);
            GLint ok;
            glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
            CHECK(ok);
            glAttachShader(program, shader);
            glDeleteShader(shader);
        }
        glBindAttribLocation(program, 0, "p");
        glLinkProgram(program);
        GLint linked;
        glGetProgramiv(program, GL_LINK_STATUS, &linked);
        CHECK(linked);
        glUseProgram(program);
        GLuint tex, fbo;
        glGenTextures(1, &tex);
        glBindTexture(GL_TEXTURE_2D, tex);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 64, 64, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
        glGenFramebuffers(1, &fbo);
        glBindFramebuffer(GL_FRAMEBUFFER, fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
        CHECK(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
        glViewport(0, 0, 64, 64);
        glEnableVertexAttribArray(0);
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, vertices);
        glDrawArrays(GL_TRIANGLES, 0, 3);
        unsigned char pixels[64 * 64 * 4];
        glReadPixels(0, 0, 64, 64, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
        CHECK(glGetError() == GL_NO_ERROR);
        for (int y = 0; y < 64; y++) {
            for (int x = 0; x < 64; x++) {
                unsigned char *p = &pixels[(y * 64 + x) * 4];
                int r = ((2*x + 1)*255 + 64)/128, g = ((2*y + 1)*255 + 64)/128;
                CHECK(abs(p[0]-r) <= 1 && abs(p[1]-g) <= 1 && abs(p[2]-64) <= 1 && p[3] == 255);
            }
        }
        glDeleteProgram(program);
        glDeleteFramebuffers(1, &fbo);
        glDeleteTextures(1, &tex);
        CHECK(eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT));
        CHECK(eglDestroyContext(dpy, ctx));
        if (round + 1 < rounds) sleep(1);
    }
    CHECK(eglTerminate(dpy));
    gbm_device_destroy(gbm);
    close(fd);
    printf("PASS %d rounds, 4096 pixels each, context recreation and one-second idle\n", rounds);
    return 0;
}
