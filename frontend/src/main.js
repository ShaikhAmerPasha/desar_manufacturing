import './index.css'
import { createApp } from 'vue'
import { FrappeUI, setConfig, frappeRequest } from 'frappe-ui'
import App from './App.vue'
import router from './router'
import { applyLocale } from './i18n'

setConfig('resourceFetcher', frappeRequest)
applyLocale()

createApp(App).use(FrappeUI).use(router).mount('#app')
