<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Badge, Button } from 'frappe-ui'
import { api } from '../api'
import { t } from '../i18n'

const router = useRouter()
const tasks = ref([])
const selected = ref(null)

const stations = computed(() => {
	const counts = {}
	tasks.value.forEach((task) => (counts[task.station] = (counts[task.station] || 0) + 1))
	return Object.entries(counts).map(([name, count]) => ({ name, count }))
})
const visible = computed(() => tasks.value.filter((task) => !selected.value || task.station === selected.value))

onMounted(async () => (tasks.value = await api('my_tasks')))

function open(task) {
	router.push(task.kind === 'Job Card' ? `/job/${task.name}` : `/inspect/${task.name}`)
}
</script>

<template>
	<main class="flex flex-col gap-6 p-6">
		<section>
			<div class="mb-3 text-sm font-semibold text-ink-gray-6">{{ t('stations').toUpperCase() }}</div>
			<div class="grid grid-cols-2 gap-4 md:grid-cols-3">
				<button
					v-for="station in stations" :key="station.name"
					class="flex min-h-28 flex-col items-start gap-1 rounded-xl border bg-surface-white p-5 text-start"
					:class="selected === station.name ? 'border-2 border-outline-gray-5' : 'border-outline-gray-2'"
					@click="selected = selected === station.name ? null : station.name"
				>
					<span class="text-lg font-semibold text-ink-gray-9">{{ station.name }}</span>
					<span class="text-4xl font-bold text-ink-gray-9">{{ station.count }}</span>
					<span class="text-sm text-ink-gray-6">{{ t('waiting') }}</span>
				</button>
			</div>
		</section>
		<section class="flex flex-col gap-3">
			<div class="text-sm font-semibold text-ink-gray-6">{{ t('next_up').toUpperCase() }}</div>
			<div v-if="!visible.length" class="rounded-xl bg-surface-white p-6 text-ink-gray-6">{{ t('no_tasks') }}</div>
			<div v-for="task in visible" :key="task.kind + task.name" class="flex items-center gap-4 rounded-xl border border-outline-gray-2 bg-surface-white p-5">
				<div class="min-w-0 flex-1">
					<div class="text-xl font-bold text-ink-gray-9">{{ task.title }}</div>
					<div class="truncate text-base text-ink-gray-6">{{ task.subtitle }}</div>
				</div>
				<Badge :label="task.status" :theme="task.status === 'Waiting' ? 'orange' : 'blue'" size="lg" />
				<Button size="xl" variant="solid" theme="gray" @click="open(task)">{{ task.status === 'Waiting' && task.kind === 'Job Card' ? t('start') : t('open') }}</Button>
			</div>
		</section>
	</main>
</template>
