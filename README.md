# FinanceAnalysis.ipynb: 
### Analysis done in 2024 for Chico Green City Coalition for Chico's city council elections. The information used to determine this is publicly available. This analysis was used to determine:
1. Who is funding the candidates?
    - What are the top donor industries (e.g., real estate, construction, PACs)?
    - How much funding comes from local vs. out-of-town donors?
    - Are there any large individual contributors who may have significant influence?
2. Are there any potential conflicts of interest?
    - Are candidates receiving large donations from companies or individuals that have pending business with the city (e.g., developers, contractors, lobbyists)?
    - Does the candidate’s policy platform align with the interests of their major donors?
    - Are donations concentrated in specific industries, signaling potential favoritism?
3. How does money impact competitiveness?
    - Is there a correlation between fundraising and polling numbers?
5. Is there a difference in funding between incumbents and challengers?
    - Do incumbents receive more institutional money compared to challengers?
    - Are first-time candidates relying more on small-dollar donations?
6. What trends exist over time?
    - Are there shifts in donor priorities (e.g., rise of environmental PACs, more small-dollar grassroots donations)?
    - Is Party A or Party B consistently raising more?
      

# Remote work trends analysis.Rmd
### Objective:
This project applies logistic regression and machine learning models to analyze employee preferences for remote work post-pandemic. The study leverages real-world workforce data to identify key factors influencing remote work adoption.

### Dataset Overview:
The dataset (remote_work_trends.csv) includes demographic, professional, and psychological factors that may influence remote work preference. Key variables include:
    - Demographics: Age, gender, country
    - Job-related factors: Job role, experience years, salary, company size
    - Remote work experience: Weekly remote work hours, tech tools used
    - Psychological factors: Job satisfaction, productivity levels, mental health impact
    - Target variable: RemoteWorkPreference (Binary: 1 = prefers remote work, 0 = does not)

### Methodology: 
1. Exploratory Data Analysis (EDA)
    - Data Cleaning: Handling missing values and converting categorical variables into factors.
    - Visualization: Stacked bar plots to analyze the proportion of employees preferring remote work by country and job role.
    - Statistical Summaries: Computed mean and standard deviation for key subgroups.
2. Logistic Regression Model
    - Full Model: A logistic regression model using all available predictors.
    - Coefficient Interpretation: Analyzed the effect of salary, job satisfaction, and company size on remote work preference.
    - Variable Selection:
        - Stepwise regression (forward, backward, and combined) was used to refine the model based on AIC/BIC criteria.
        - Likelihood Ratio Test (LRT) determined if a reduced model was statistically equivalent to the full model.
3. Machine Learning Approaches
    - Decision Tree Model: Built a classification tree with cross-validation to predict remote work preference.
    - Regularization Techniques:
        - Ridge Regression: Penalized model to address multicollinearity.
        - Lasso Regression: Selected the most significant predictors by shrinking non-influential coefficients to zero.
        - Elastic Net: Combined ridge and lasso penalties for optimal feature selection.
        - Group Lasso: Grouped variables (e.g., experience and job satisfaction) to improve interpretability.
4. Model Evaluation and Prediction
    - Probability Predictions: Computed average predicted probabilities for each model on the test set.
    - Classification Threshold (0.3): Converted probability outputs into binary classifications.
    - Performance Metrics:
        - Confusion matrices and classification metrics (Accuracy, Precision, Recall, F1-score)
        - Comparison of model effectiveness in identifying remote work preference.
        - True Positive Rate (Recall) analysis to determine the best model.
          
### Key Findings
    - Employees with higher job satisfaction and more remote work hours were significantly more likely to prefer remote work.
    - Company size influenced preference—employees in large companies were more inclined toward remote work.
    - Mental health impact (positive or neutral) was a strong predictor of remote work preference.
    - Lasso and Elastic Net regression identified the most influential predictors while maintaining model simplicity.
    - Decision trees and logistic regression provided interpretable models, while regularization methods improved predictive performance.

# Searchable_File_Counts_SQL.sql
### Purpose:
The analysis was conducted in order to find any discrepancies in files moving through a data pipeline. The pipeline layers are:
    - Acquisition
    - Ingestion (raw and messy)
    - Standardization (flattened and structured)
    - Shared (separated into different tables for downstream users)

These layers contain claims, remits, and physician data, but lack consistent keys to link across them. The only place with file date information is an external acquisition table. To verify expected data availabilities, I extracted and standardized file names from four different fields across layers, then joined them back to the acquisition table. An example approach for one layer was joining a shared table on stripped file paths, grouping by year, and counting distinct files—accounting for overlaps due to multiple remits/claims per file. This revealed that only 35% of 2023 data were available, prompting me to contact our ETL team, which quickly led to a solution. This analysis was created in Databricks, incorporating user-defined variables (parameters, denoted by `{}`) so future evaluations can be easily run with different data feeds and clients.

# Status of Client x12 Files.py
### Purpose: 
This analysis is necessary during onboarding to determine if a client's data have made it through each data pipeline process. If it is discovered that they do not, the configurations for the pipelines were reviewed and either re-configured or created (if they did not exist).
