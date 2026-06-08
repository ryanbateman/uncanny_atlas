<script lang="ts">
	// Small discoverable info icon with an accessible hover/focus tooltip.
	let { text }: { text: string } = $props();
</script>

<button type="button" class="hint" title={text} aria-label={text}>i</button>
