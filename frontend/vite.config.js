import path from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'

export default defineConfig({
	plugins: [
		frappeui({
			frappeProxy: true,
			lucideIcons: true,
			jinjaBootData: true,
			buildConfig: {
				indexHtmlPath: '../desar_manufacturing/www/shop_floor.html',
			},
		}),
		vue(),
	],
	resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
	optimizeDeps: { exclude: ['frappe-ui'] },
})
