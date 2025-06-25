# Contributing

In order to contribute without having to be directly added as a contributor to this project it is best to follow the well known forking strategy. Follow the steps below to fork dashboard and contribute back to the project from your personal fork.

## Navigate and Fork dashboard Repository

Navigate to the [dashboard project](https://github.com/unc-network/dashboard) on GitHub. Once you're on the main repository page click on the fork button.

You'll then be brought to a screen to complete the fork into your personal user repository.

You'll finally be redirected to your fork, which is linked to the parent repository.

## Clone the dashboard repository

Next you'll need to clone your forked repository.

```console
% git clone git@github.com:<gituser>/dashboard.git
Cloning into 'dashboard'...
remote: Enumerating objects: 484, done.
remote: Counting objects: 100% (79/79), done.
remote: Compressing objects: 100% (66/66), done.
remote: Total 484 (delta 10), reused 28 (delta 7), pack-reused 405 (from 1)
Receiving objects: 100% (484/484), 109.08 KiB | 4.54 MiB/s, done.
Resolving deltas: 100% (225/225), done.
```

Once your forked repository is cloned you can change into the dashboard directory.

```console
% cd dashboard
```

Finally you can check the status of git.

```console
% git status
```

Git Status should look similar to the following:

```console
% git status
On branch develop
Your branch is up to date with 'origin/develop'.

nothing to commit, working tree clean

```

## Create a branch for your work

```console
% git checkout -b my_cool_work origin/develop
branch 'my_cool_work' set up to track 'origin/develop'.
Switched to a new branch 'my_cool_work'
```

## Make your changes pass the linters and tests

At the end of your changes the linters and unit tests MUST all pass.

## Submit your PR to the dashboard repository

Place a clear statement regarding the purpose of the PR (bug it is fixing, feature it is adding).

For any more meaningful feature, you should open a GitHub issue or discussion first and make sure that we agree on implementing this feature.

The PR will will be sourced from your forked repository + the forked repository branch in use, with the destination of dashboard's develop branch.
