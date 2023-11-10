from collections import defaultdict
def get_noncore_repo_changelog_errors(git_diff: str, suffix: str, private: bool = False) -> list[tuple[str, int, str]]:
    '''
    Extras and Marketplace repos manage their changelogs as a single file.

    We make sure that what contributors write to it follows are formatting conventions.
    '''
def extract_filenames(git_diff: str) -> Iterator[str]:
    for modification in re.split(r'^diff --git ', git_diff, flags=re.MULTILINE):
        if not modification:
            continue

        # a/file b/file
        # new file mode 100644
        # index 0000000000..089fd64579
        # --- a/file
        # +++ b/file
        metadata, *_ = re.split(r'^@@ ', modification, flags=re.MULTILINE)
        *_, before, after = metadata.strip().splitlines()

        # Binary files /dev/null and b/foo/archive.tar.gz differ
        binary_indicator = 'Binary files '
        if after.startswith(binary_indicator):
            line = after[len(binary_indicator) :].rsplit(maxsplit=1)[0]
            if line.startswith('/dev/null and '):
                filename = line.split(maxsplit=2)[-1][2:]
            elif line.endswith(' and /dev/null'):
                filename = line.split(maxsplit=2)[0][2:]
            else:
                _, _, filename = line.partition(' and b/')

            yield filename
            continue

        # --- a/file
        # +++ /dev/null
        before = before.split(maxsplit=1)[1]
        after = after.split(maxsplit=1)[1]
        filename = before[2:] if after == '/dev/null' else after[2:]
        yield filename


def get_core_repo_changelog_errors(git_diff: str, pr_number: int) -> list[str]:
    '''
    The integrations-core repo uses towncrier to stitch a release changelog from entry files.

    The validation reflects this so it's different from extras and marketplace.
    '''
    targets: defaultdict[str, list[str]] = defaultdict(list)
    for filename in extract_filenames(git_diff):
        target, _, path = filename.partition('/')
        if path:
            targets[target].append(path)

    fragments_dir = 'changelog.d'
    errors: list[str] = []
    for target, files in sorted(targets.items()):
        if not requires_changelog(target, iter(files)):
            continue
        changelog_entries = [f for f in files if f.startswith(fragments_dir)]
        if not changelog_entries:
            errors.append(
                f'Package "{target}" is missing a changelog entry for the following changes:\n'
                + '\n'.join(f'- {f}' for f in files)
                + 'Please run `ddev release changelog new` to add missing changelog entries.'
            )
            continue
        for entry_path in changelog_entries:
            entry_parents, entry_fname = os.path.split(entry_path)
            entry_pr_num, _, entry_fname_rest = entry_fname.partition(".")
            if int(entry_pr_num) != pr_number:
                correct_entry_path = os.path.join(entry_parents, f'{pr_number}.{entry_fname_rest}')
                errors.append(
                    f'Please rename changelog entry file "{target}/{entry_path}" to "{correct_entry_path}". '
                    + 'This way your changelog entry matches the PR number.'
                )

    return errors


def convert_to_messages(errors, on_ci):
    for relative_path, line_number, message in errors:
        yield (
            f'::error file={relative_path},line={line_number}::{message}'
            if on_ci
            else f'{relative_path}, line {line_number}: {message}'
        )


def changelog_impl(*, ref: str, diff_file: str, pr_file: str, private: bool, repo: str) -> None:
    errors = (
        get_core_repo_changelog_errors(git_diff, pr_number)
        if repo == 'core'
        else get_noncore_repo_changelog_errors(git_diff, changelog_entry_suffix(pr_number, pr_url), private=private)
    )
    for message in errors if repo == "core" else convert_to_messages(errors, on_ci):
        formatted = '%0A'.join(message.splitlines()) if on_ci else message
        print(formatted)
    parser.add_argument('--repo', default='core')