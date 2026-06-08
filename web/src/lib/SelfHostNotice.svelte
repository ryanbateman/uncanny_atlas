<script lang="ts">
	// Shown on the public, read-only edition in place of any verbatim-comment surface.
	let { what = 'Example comments' }: { what?: string } = $props();
</script>

<div class="self-host-notice">
	<strong>{what} aren't shown in this public edition.</strong>
	<span>
		To stay within Reddit's content terms, the public site serves aggregate data only — no
		verbatim comments or usernames. Run Uncanny Atlas yourself to browse them.
		<a href="/#editions">Why, and how →</a>
	</span>
</div>

<style>
	.self-host-notice {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: var(--space-4);
		border: 1px dashed var(--border);
		border-radius: var(--radius);
		background: var(--surface-2);
		color: var(--muted);
		font-size: var(--text-sm);
		line-height: 1.5;
	}
	.self-host-notice strong {
		color: var(--text);
	}
</style>
