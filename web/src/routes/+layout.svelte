<script lang="ts">
	import '../app.css';
	import '@fontsource-variable/inter/index.css';
	import { page } from '$app/state';
	import { afterNavigate } from '$app/navigation';

	let { children, data } = $props();

	// Mobile: the sidebar collapses to a top bar; this toggles the nav drawer.
	let navOpen = $state(false);
	// Dismiss the drawer whenever a navigation completes (i.e. a link was followed).
	afterNavigate(() => (navOpen = false));

	// Publication detail — keep in sync with the About page (web/src/routes/+page.svelte).
	const REPO_URL = 'https://github.com/ryanbateman/uncanny_atlas';

	const explore = [
		{ href: '/explore', label: 'Overview' },
		{ href: '/explore/indicators', label: 'Top Indicators' },
		{ href: '/explore/lookup', label: 'Inspect indicator', commentOnly: true },
		{ href: '/explore/matches', label: 'Semantic matches', commentOnly: true },
		{ href: '/explore/pipeline', label: 'Pipeline status' }
	];
	const curate = [
		{ href: '/curate/indicators', label: 'Categorise / seeds' },
		{ href: '/curate/merge', label: 'Merge / canonical' },
		{ href: '/curate/emerge', label: 'Emerging' }
	];

	// Read-only public edition: rather than hide the write/comment views, show them
	// grayed-out + disabled with a hover explanation.
	const COMMENT_OFF =
		'Per-comment views are off on the public read-only site — run Uncanny Atlas yourself to use them.';
	const CURATE_OFF =
		'Curation is disabled on the public read-only site — run Uncanny Atlas yourself to edit.';

	const isActive = (href: string) => page.url.pathname === href;

	// Dev-only: flip the read-only *view* (nav, example surfaces, About note) via a
	// cookie the server reads in dev, so layouts can be debugged in both states
	// without restarting. See hooks.server.ts.
	function setReadonlyView(on: boolean) {
		document.cookie = `ua_ro=${on ? '1' : '0'};path=/;max-age=86400;samesite=lax`;
		location.reload();
	}
</script>

<svelte:head>
	<title>Uncanny Atlas</title>
</svelte:head>

{#snippet navItem(href: string, label: string, disabled: boolean, reason: string)}
	{#if disabled}
		<!-- href-less anchor: keeps the nav styling but isn't a link; tooltip explains why. -->
		<a class="disabled" aria-disabled="true" title={reason}>{label}</a>
	{:else}
		<a href={href} class:active={isActive(href)}>{label}</a>
	{/if}
{/snippet}

<div class="app">
	<aside class="sidebar" class:nav-open={navOpen}>
		<div class="sidebar-head">
			<h1>Uncanny<br />Atlas <span class="title-mark">+</span></h1>
			<button
				class="nav-toggle"
				aria-label="Toggle navigation"
				aria-expanded={navOpen}
				onclick={() => (navOpen = !navOpen)}
			>
				<span></span><span></span><span></span>
			</button>
		</div>

		<div class="sidebar-body">
			<div class="tagline">how people spot AI images</div>

			<!-- Navigating dismisses the mobile drawer (see afterNavigate below). -->
			<nav class="nav">
				<div class="nav-group">
					<a href="/" class:active={isActive('/')}>About</a>
					<a href="/how-it-works" class:active={isActive('/how-it-works')}>How it works</a>
					<a href="/runbook" class:active={isActive('/runbook')}>Run book</a>
				</div>

				<div class="nav-group">
					<div class="label">Explore</div>
					{#each explore as item (item.href)}
						{@render navItem(item.href, item.label, !!(data.readonly && item.commentOnly), COMMENT_OFF)}
					{/each}
				</div>

				<div class="nav-group">
					<div class="label">Curate</div>
					{#each curate as item (item.href)}
						{@render navItem(item.href, item.label, data.readonly, CURATE_OFF)}
					{/each}
				</div>
			</nav>

			{#if data.dev}
				<label class="dev-toggle" title="Dev only: switch every page between the read-only public view and the read/write view.">
					<input
						type="checkbox"
						checked={data.readonly}
						onchange={(e) => setReadonlyView(e.currentTarget.checked)}
					/>
					<span>Read-only view <span class="dev-tag">dev</span></span>
				</label>
			{/if}

			<div class="sidebar-credit">
				Created by <a
					href="https://boat.horse"
					title="Once I worked for a year manually building a huge vector space of all Yahoo content using the world's largest Hadoop cluster but got made redundant when Marissa Meyer pivoted the company to iPad digital magazines, lol."
					>Ryan Bateman</a
				>
			</div>
		</div>
	</aside>

	<main>
		{@render children()}
		<footer class="site-footer">
			<span class="mark">Uncanny Atlas</span>
			<span class="sep">·</span>
			<a href="/">About</a>
			<a href={REPO_URL}>GitHub</a>
			<a href={`${REPO_URL}/blob/main/LICENSE`}>MIT License</a>
			{#if data.snapshot?.date}
				<span class="sep">·</span>
				<span class="snapshot" title="Latest activity in the dataset — quote numbers against this date.">
					Data to {data.snapshot.date} · {data.snapshot.comments.toLocaleString('en-US')} comments
				</span>
			{/if}
		</footer>
	</main>
</div>

<style>
	.site-footer {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: var(--space-3);
		margin-top: var(--space-7);
		padding-top: var(--space-4);
		border-top: 1px solid var(--border);
		color: var(--muted);
		font-size: var(--text-xs);
	}
	.site-footer .mark {
		font-family: var(--font-display);
		font-weight: 700;
		color: var(--text);
	}
	/* The ornamental cross after the wordmark — the 'ss01' alternate of '+' in Captain
	   Edward. Falls back to a plain '+' where the font isn't loaded (open-source build). */
	.sidebar h1 .title-mark {
		font-family: var(--font-display);
		font-feature-settings: 'ss01' 1;
		color: var(--accent);
	}
	.site-footer .sep {
		opacity: 0.5;
	}
	.site-footer a {
		color: var(--muted);
	}
	.site-footer a:hover {
		color: var(--accent);
	}

	.dev-toggle {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin-top: var(--space-5);
		padding: var(--space-2) 10px;
		border: 1px dashed var(--border);
		border-radius: var(--radius-sm);
		font-size: var(--text-xs);
		color: var(--muted);
		cursor: pointer;
		user-select: none;
	}
	.dev-toggle input {
		accent-color: var(--accent);
		margin: 0;
	}
	.dev-tag {
		display: inline-block;
		padding: 0 5px;
		border-radius: 4px;
		background: var(--surface-2);
		color: var(--muted);
		font-size: var(--text-2xs);
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}

	/* Author credit pinned to the bottom of the sidebar (the sidebar is a flex column). */
	.sidebar-credit {
		margin-top: auto;
		padding-top: var(--space-5);
		color: var(--muted);
		font-size: var(--text-xs);
	}
</style>
