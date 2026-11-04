Contributing to nctoolkit

🎉 Thank you for your interest in contributing to nctoolkit! Your efforts help improve this tool for the entire community. Whether you're fixing bugs, adding new features, or enhancing documentation, your contributions are invaluable. Let's make this project even better together! 🎉

How to Contribute

To contribute, please follow these steps:

1. Fork the Repository
Click the "Fork" button at the top right of this page to create a copy of this repository under your GitHub account.

2. Clone and Set Up the Repository
After forking, open your terminal, clone the repository to your local machine, and navigate into the project directory:
git clone https://github.com/your-username/nctoolkit.git
cd nctoolkit

3. Create a New Branch
Create a new branch for your contribution to keep your changes organized and separated from the main codebase:
git checkout -b feature/your-feature-name

4. Make Your Changes
Add your feature, fix bugs, or improve documentation. Be sure to:
Keep your changes focused on a single feature or fix for easier review.
Test your modifications to ensure they work as intended.
CI runs the tests in 3 parallel groups using pytest-split, balanced by the timings in `.test_durations`. To refresh that file after adding many tests, run `pytest tests/test*.py --store-durations --durations-path .test_durations`.
Follow any coding style guidelines noted in the project.

5. Commit Your Changes
When you’re ready, stage and commit your changes with a clear, descriptive commit message:
git add .
git commit -m "Add detailed description of your changes here"

6. Push to Your Fork
Push your branch to your GitHub repository:
git push origin feature/your-feature-name

7. Submit a Pull Request (PR)
Go to the original nctoolkit repository on GitHub.
Click the "New Pull Request" button and select your branch.
Include a detailed description of your changes to help reviewers understand your contribution.
