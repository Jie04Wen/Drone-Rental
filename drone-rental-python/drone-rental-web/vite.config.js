import {defineConfig} from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import {ElementPlusResolver} from 'unplugin-vue-components/resolvers'
import path from 'path'

const backendTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8080'
const websocketTarget = backendTarget.replace(/^http/, 'ws')

// 构建体积分析（可选，需 npm i -D rollup-plugin-visualizer）
let visualizer = null
try {
    const {visualizer: Plugin} = await import('rollup-plugin-visualizer')
    visualizer = Plugin({open: false, filename: 'dist/stats.html', gzipSize: true})
} catch { /* 未安装时跳过 */
}

export default defineConfig({
    plugins: [
        vue(),
        AutoImport({
            resolvers: [ElementPlusResolver()],
            imports: ['vue', 'vue-router', 'pinia'],
            dts: false
        }),
        Components({
            resolvers: [ElementPlusResolver({importStyle: 'sass'})],
            dts: false
        }),
        visualizer
    ],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, 'src')
        }
    },
    css: {
        preprocessorOptions: {
            scss: {
                api: 'modern-compiler',
                silenceDeprecations: ['legacy-js-api', 'import'],
                additionalData: (source, filename) => {
                    // 跳过 node_modules 和 variables.scss 自身
                    if (filename.includes('node_modules') || filename.includes('variables.scss')) {
                        return source
                    }
                    return `@import "@/assets/styles/variables.scss";\n${source}`
                }
            }
        }
    },
    server: {
        port: 3000,
        allowedHosts: ['.trycloudflare.com'],
        proxy: {
            '/api': {
                target: backendTarget,
                changeOrigin: true,
                configure: (proxy) => {
                    proxy.on('proxyRes', (proxyRes) => {
                        const ct = proxyRes.headers['content-type'] || ''
                        if (ct.includes('text/event-stream')) {
                            proxyRes.headers['cache-control'] = 'no-cache, no-transform'
                            proxyRes.headers['x-accel-buffering'] = 'no'
                        }
                    })
                }
            },
            '/ws': {
                target: websocketTarget,
                ws: true,
                changeOrigin: true
            }
        }
    },
    build: {
        chunkSizeWarningLimit: 800,
        // rollupOptions: {
        //     output: {
        //         manualChunks: {
        //             'echarts-vendor': ['echarts'],
        //             'element-plus-vendor': ['element-plus', '@element-plus/icons-vue'],
        //             'vue-vendor': ['vue', 'vue-router', 'pinia']
        //         }
        //     }
        // }
    }
})
