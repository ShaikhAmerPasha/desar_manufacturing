<script setup>
import { Button } from 'frappe-ui'
import { useRouter } from 'vue-router'
import { t, toggleLocale } from '../i18n'

defineProps({ user: Object, title: String, back: Boolean })
const router = useRouter()
</script>

<template>
	<header class="flex h-16 items-center gap-3 border-b border-outline-gray-2 bg-surface-white px-6">
		<Button v-if="back" size="lg" variant="outline" @click="router.back()">{{ t('back') }}</Button>
		<div class="min-w-0 flex-1">
			<div class="truncate text-lg font-semibold text-ink-gray-9">{{ title || `${t('hello')}, ${user?.full_name || ''}` }}</div>
		</div>
		<Button v-if="user?.is_supervisor" size="lg" variant="subtle" @click="router.push('/assign')">{{ t('assign_work') }}</Button>
		<Button size="lg" variant="outline" @click="toggleLocale">{{ t('language') }}</Button>
	</header>
</template>
