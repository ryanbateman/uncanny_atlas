<script lang="ts">
	// Per-chart/table media filter ('' = All). One component so the option list
	// has a single home; styling matches the other in-header chart controls.
	let { value = $bindable('') }: { value?: string } = $props();
</script>

<select bind:value class="chart-mode" aria-label="Media type">
	<option value="">All media</option>
	<option value="video">Video</option>
	<option value="image">Image</option>
	<option value="text">Text</option>
	<option value="other">Other</option>
</select>
