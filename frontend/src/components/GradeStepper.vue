<script setup>
import { Button } from 'frappe-ui'

const props = defineProps({ modelValue: { type: Number, default: 0 }, grade: String, label: String, readonly: Boolean })
const emit = defineEmits(['update:modelValue'])
const step = (delta) => emit('update:modelValue', Math.max(0, props.modelValue + delta))
const tone = { A: 'bg-surface-green-2 text-ink-green-3', B: 'bg-surface-amber-2 text-ink-amber-3', C: 'bg-surface-red-2 text-ink-red-4' }
</script>

<template>
	<div class="flex flex-1 flex-col gap-2 rounded-xl p-4" :class="tone[grade] || 'bg-surface-gray-2 text-ink-gray-8'">
		<div class="text-sm font-semibold">{{ label || grade }}</div>
		<div class="flex items-center justify-between gap-2">
			<Button v-if="!readonly" size="xl" variant="outline" class="!h-14 !w-14 text-2xl" @click="step(-1)">−</Button>
			<div class="min-w-10 text-center text-4xl font-bold">{{ modelValue }}</div>
			<Button v-if="!readonly" size="xl" variant="outline" class="!h-14 !w-14 text-2xl" @click="step(1)">+</Button>
		</div>
	</div>
</template>
