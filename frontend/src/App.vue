<script setup>
import { onMounted, provide, ref } from 'vue'
import { call } from 'frappe-ui'
import { isRtl } from './i18n'
import TopBar from './components/TopBar.vue'

const user = ref(null)
provide('user', user)

onMounted(async () => {
	try {
		const name = await call('frappe.auth.get_logged_user')
		const info = await call('frappe.client.get_value', { doctype: 'User', filters: { name }, fieldname: ['full_name'] })
		const roles = await call('frappe.core.doctype.user.user.get_roles', { arg: name }).catch(() => [])
		const supervisor = roles.includes('DESAR Supervisor') || roles.includes('System Manager')
		user.value = { name, full_name: info?.full_name || name, is_supervisor: supervisor }
	} catch (error) {
		window.location.href = '/login?redirect-to=/shop-floor'
	}
})
</script>

<template>
	<div class="min-h-screen bg-surface-gray-1 text-ink-gray-9" :dir="isRtl ? 'rtl' : 'ltr'">
		<TopBar v-if="user && $route.name === 'Tasks'" :user="user" />
		<router-view v-if="user" :user="user" />
	</div>
</template>
