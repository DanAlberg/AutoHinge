import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.dates as mdates
import numpy as np
import os
import seaborn as sns

def database():
        # Use the absolute path to the actual profiles.db
    db_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'profiles.db')
    
    if not os.path.exists(db_file):
        print(f"Error: Database file not found at {db_file}")
        return None

    # Pull all data
    # sqlite3 connection with uri=True and mode=rw prevents creating a new db if it doesn't exist
    conn = sqlite3.connect(f"file:{db_file}?mode=rw", uri=True)
    query = """
    SELECT timestamp, score_breakdown, verdict, matched, Age 
    FROM profiles 
    WHERE timestamp IS NOT NULL 
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("No data found in database.")
        return None

    # Parse datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    # Parse decision
    def get_decision(row):
        v = str(row['verdict']).upper()
        if 'PICKUP' in v or 'LIKE' in v:
            return 1
        return 0

    df['is_like'] = df.apply(get_decision, axis=1)
    df['is_eval'] = 1
    df['is_match'] = df['matched'].fillna(0).astype(int)

    return df


def generate_daily_ratio_graph(df):
    output_dir = 'graphs'
    output_file = os.path.join(output_dir, '01_daily_activity.png')
    os.makedirs(output_dir, exist_ok=True)

    df = df.copy()
    df = df[df['timestamp'] >= '2026-04-01'].copy()
    df['date'] = df['timestamp'].dt.date

    # Group by date
    daily = df.groupby('date').agg(
        evals=('is_eval', 'sum'),
        likes=('is_like', 'sum'),
        matches=('is_match', 'sum')
    ).reset_index()

    daily['date'] = pd.to_datetime(daily['date'])
    daily = daily.sort_values('date')

    # Reindex to fill missing dates with 0 to ensure accurate rolling windows
    if not daily.empty:
        full_range = pd.date_range(start=daily['date'].min(), end=daily['date'].max(), freq='D')
        daily = daily.set_index('date').reindex(full_range).fillna(0).reset_index()
        daily.rename(columns={'index': 'date'}, inplace=True)

    # 1. Per day Like Ratio (no rolling)
    daily['daily_like_ratio'] = np.where(daily['evals'] > 0, daily['likes'] / daily['evals'], np.nan)

    # 2. 3-day Rolling Match Ratio
    daily['rolling_likes_3d'] = daily['likes'].rolling(window=3, min_periods=1, center=True).sum()
    daily['rolling_matches_3d'] = daily['matches'].rolling(window=3, min_periods=1, center=True).sum()
    daily['rolling_match_ratio_3d'] = np.where(daily['rolling_likes_3d'] > 0, daily['rolling_matches_3d'] / daily['rolling_likes_3d'], np.nan)

    # Filter for plotting: only days with >= 3 profiles evaluated
    plot_data = daily[daily['evals'] >= 3].copy()

    if plot_data.empty:
        print("Not enough data to plot (requires days with >= 3 evaluations).")
        return

    # Plotting
    fig, ax1 = plt.subplots(figsize=(16, 8))
    ax2 = ax1.twinx()

    # Bar chart for evaluated profiles
    ax1.bar(plot_data['date'], plot_data['evals'], color='#e0e2e4', label='Profiles Evaluated', width=0.8)

    # Line charts for ratios
    ax2.plot(plot_data['date'], plot_data['daily_like_ratio'], color='#E74C3C', marker='o', linewidth=2, markersize=6, label='Like Ratio (Daily, No Rolling)')
    ax2.plot(plot_data['date'], plot_data['rolling_match_ratio_3d'], color='#2ECC71', marker='s', linewidth=3, markersize=8, label='Match Ratio (3-Day Rolling)')

    # Force the lines (ax2) to render in front of the bars (ax1)
    ax1.set_zorder(1)
    ax2.set_zorder(2)
    ax2.patch.set_visible(False)

    # Formatting
    ax1.set_title('Daily Activity vs. Like & Match Ratios (Filtered: \u2265 3 Evals, Apr 2026 Onwards)', fontsize=16, fontweight='bold', pad=15)
    ax1.set_xlabel('Date', fontweight='bold', fontsize=12, labelpad=10)
    ax1.set_ylabel('Number of Profiles Evaluated', color='grey', fontweight='bold', fontsize=12)
    ax2.set_ylabel('Ratio Percentage', color='black', fontweight='bold', fontsize=12)

    # Axis ticks and limits
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax1.tick_params(axis='x', rotation=45)

    # Styling
    ax1.grid(True, axis='y', color='lightgrey', linestyle='--', linewidth=0.7)

    for spine in ['top', 'right', 'left', 'bottom']:
        ax1.spines[spine].set_color('lightgrey')
        ax2.spines[spine].set_color('lightgrey')
    ax2.spines['top'].set_visible(False)
    ax1.spines['top'].set_visible(False)

    # Legend
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', fontsize=11, frameon=True, shadow=True)

    plt.tight_layout()
    plt.savefig(output_file, dpi=150)
    plt.close()
    
    print(f"Graph successfully generated and saved to: {output_file}")




def generate_heatmap(df):
    df = df.copy()
    # Create Day of Week and Hour columns
    df['dow'] = df['timestamp'].dt.day_name()
    df['hour'] = df['timestamp'].dt.hour
    
    # Order the days logically
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    df['dow'] = pd.Categorical(df['dow'], categories=days_order, ordered=True)
    
    # Bin the hours to kill noise
    bins = [0, 6, 12, 18, 24]
    labels = ['Late Night (00-06)', 'Morning (06-12)', 'Afternoon (12-18)', 'Evening (18-24)']
    df['time_block'] = pd.cut(df['hour'], bins=bins, labels=labels, right=False)
    
    # Calculate match ratio per block
    # Note: Filter to df[df['is_like'] == 1] first so you are only looking at your Likes
    likes_only = df[df['is_like'] == 1]
    
    agg_df = likes_only.groupby(['dow', 'time_block'], observed=False).agg(
        match_ratio=('is_match', 'mean'),
        likes_count=('is_match', 'count')
    ).reset_index()

    # Set ratio to NaN if likes < 5
    agg_df['match_ratio'] = np.where(agg_df['likes_count'] >= 5, agg_df['match_ratio'], np.nan)
    
    pivot_ratio = agg_df.pivot(index='dow', columns='time_block', values='match_ratio')
    pivot_count = agg_df.pivot(index='dow', columns='time_block', values='likes_count')
    
    # Create custom annotations
    annot_labels = pivot_ratio.copy().astype(str)
    for i in range(pivot_ratio.shape[0]):
        for j in range(pivot_ratio.shape[1]):
            r = pivot_ratio.iloc[i, j]
            c = pivot_count.iloc[i, j]
            if pd.isna(r):
                annot_labels.iloc[i, j] = ""
            else:
                annot_labels.iloc[i, j] = f"{r:.1%}\n(n={int(c)})"
    
    # Plot Heatmap
    plt.figure(figsize=(10, 6))
    sns.heatmap(pivot_ratio, annot=annot_labels, fmt="", cmap="Greens", cbar_kws={'label': 'Match Ratio'})
    plt.title('Match Ratio "Sweet Spots" (Day vs. Time)')
    os.makedirs('graphs', exist_ok=True)
    plt.tight_layout()
    plt.savefig('graphs/02_best_times_heatmap.png')
    plt.close()   

def generate_tod_rolling(df):
    # Filter to only look at profiles you liked
    likes_only = df[df['is_like'] == 1].copy()
    likes_only['hour'] = likes_only['timestamp'].dt.hour
    
    # Aggregate by hour
    tod = likes_only.groupby('hour').agg(
        likes=('is_like', 'sum'),
        matches=('is_match', 'sum')
    ).reset_index()
    
    # Ensure all 24 hours exist in the dataframe to prevent gaps in the graph
    all_hours = pd.DataFrame({'hour': range(24)})
    tod = all_hours.merge(tod, on='hour', how='left').fillna(0)
    
    # Cyclical wrap-around for rolling average (so midnight smoothly connects to 11 PM)
    padded = pd.concat([tod.iloc[-1:], tod, tod.iloc[:1]]).reset_index(drop=True)
    padded['rolling_likes'] = padded['likes'].rolling(window=3, center=True).sum()
    padded['rolling_matches'] = padded['matches'].rolling(window=3, center=True).sum()
    
    # Extract the original 24 hours back out
    smoothed = padded.iloc[1:25].copy().reset_index(drop=True)
    
    # Only calculate ratio if you sent at least 5 likes in that 3-hour window to kill noise
    smoothed['smoothed_ratio'] = np.where(smoothed['rolling_likes'] >= 5, 
                                          smoothed['rolling_matches'] / smoothed['rolling_likes'], 
                                          np.nan)
    
    # --- Plotting Code ---
    fig, ax1 = plt.subplots(figsize=(14, 7))
    ax2 = ax1.twinx()
    
    # Bar chart for volume (Likes Sent)
    ax1.bar(smoothed['hour'], smoothed['rolling_likes'], color='#e0e2e4', label='Likes Sent (3h Rolling Volume)')
    
    # Line chart for Match Ratio
    ax2.plot(smoothed['hour'], smoothed['smoothed_ratio'], color='#2ECC71', marker='o', linewidth=3, markersize=8, label='Match Ratio (3h Rolling)')
    
    # Layering
    ax1.set_zorder(1)
    ax2.set_zorder(2)
    ax2.patch.set_visible(False)
    
    # Formatting
    ax1.set_title('Match Ratio by Time of Day (3-Hour Cyclical Rolling Avg)', fontsize=16, fontweight='bold', pad=15)
    ax1.set_xlabel('Hour of Day', fontweight='bold', fontsize=12, labelpad=10)
    ax1.set_ylabel('Likes Sent Volume', color='grey', fontweight='bold', fontsize=12)
    ax2.set_ylabel('Match Ratio Percentage', color='black', fontweight='bold', fontsize=12)
    
    # X-Axis labels (24 hour format)
    hours_labels = [f"{h:02d}:00" for h in range(24)]
    ax1.set_xticks(range(24))
    ax1.set_xticklabels(hours_labels, rotation=45)
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    
    # Styling
    ax1.grid(True, axis='y', color='lightgrey', linestyle='--', linewidth=0.7)
    for spine in ['top', 'right', 'left', 'bottom']:
        ax1.spines[spine].set_color('lightgrey')
        ax2.spines[spine].set_color('lightgrey')
    ax2.spines['top'].set_visible(False)
    ax1.spines['top'].set_visible(False)
    
    # Legend
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', fontsize=11, frameon=True, shadow=True)
    
    os.makedirs('graphs', exist_ok=True)
    plt.tight_layout()
    plt.savefig('graphs/03_time_of_day_trends.png', dpi=150)
    plt.close()
    print("Graph successfully generated and saved to: graphs/03_time_of_day_trends.png")

def generate_tod_rolling_recent(df):
    # Filter for the last 3 months
    max_date = df['timestamp'].max()
    cutoff_date = max_date - pd.DateOffset(months=3)
    df_recent = df[df['timestamp'] >= cutoff_date].copy()
    
    # Filter to only look at profiles you liked
    likes_only = df_recent[df_recent['is_like'] == 1].copy()
    
    # If no data in the last 3 months, return
    if likes_only.empty:
        print("No recent data for 3-month TOD graph.")
        return
        
    likes_only['hour'] = likes_only['timestamp'].dt.hour
    
    # Aggregate by hour
    tod = likes_only.groupby('hour').agg(
        likes=('is_like', 'sum'),
        matches=('is_match', 'sum')
    ).reset_index()
    
    # Ensure all 24 hours exist in the dataframe to prevent gaps in the graph
    all_hours = pd.DataFrame({'hour': range(24)})
    tod = all_hours.merge(tod, on='hour', how='left').fillna(0)
    
    # Cyclical wrap-around for rolling average (so midnight smoothly connects to 11 PM)
    padded = pd.concat([tod.iloc[-1:], tod, tod.iloc[:1]]).reset_index(drop=True)
    padded['rolling_likes'] = padded['likes'].rolling(window=3, center=True).sum()
    padded['rolling_matches'] = padded['matches'].rolling(window=3, center=True).sum()
    
    # Extract the original 24 hours back out
    smoothed = padded.iloc[1:25].copy().reset_index(drop=True)
    
    # Only calculate ratio if you sent at least 5 likes in that 3-hour window to kill noise
    smoothed['smoothed_ratio'] = np.where(smoothed['rolling_likes'] >= 5, 
                                          smoothed['rolling_matches'] / smoothed['rolling_likes'], 
                                          np.nan)
    
    # --- Plotting Code ---
    fig, ax1 = plt.subplots(figsize=(14, 7))
    ax2 = ax1.twinx()
    
    # Bar chart for volume (Likes Sent)
    ax1.bar(smoothed['hour'], smoothed['rolling_likes'], color='#e0e2e4', label='Likes Sent (3h Rolling Volume)')
    
    # Line chart for Match Ratio
    ax2.plot(smoothed['hour'], smoothed['smoothed_ratio'], color='#2ECC71', marker='o', linewidth=3, markersize=8, label='Match Ratio (3h Rolling)')
    
    # Layering
    ax1.set_zorder(1)
    ax2.set_zorder(2)
    ax2.patch.set_visible(False)
    
    # Formatting
    ax1.set_title('Match Ratio by Time of Day (Last 3 Months, 3-Hour Rolling Avg)', fontsize=16, fontweight='bold', pad=15)
    ax1.set_xlabel('Hour of Day', fontweight='bold', fontsize=12, labelpad=10)
    ax1.set_ylabel('Likes Sent Volume', color='grey', fontweight='bold', fontsize=12)
    ax2.set_ylabel('Match Ratio Percentage', color='black', fontweight='bold', fontsize=12)
    
    # X-Axis labels (24 hour format)
    hours_labels = [f"{h:02d}:00" for h in range(24)]
    ax1.set_xticks(range(24))
    ax1.set_xticklabels(hours_labels, rotation=45)
    ax2.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    
    # Styling
    ax1.grid(True, axis='y', color='lightgrey', linestyle='--', linewidth=0.7)
    for spine in ['top', 'right', 'left', 'bottom']:
        ax1.spines[spine].set_color('lightgrey')
        ax2.spines[spine].set_color('lightgrey')
    ax2.spines['top'].set_visible(False)
    ax1.spines['top'].set_visible(False)
    
    # Legend
    lines_1, labels_1 = ax1.get_legend_handles_labels()
    lines_2, labels_2 = ax2.get_legend_handles_labels()
    ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', fontsize=11, frameon=True, shadow=True)
    
    os.makedirs('graphs', exist_ok=True)
    plt.tight_layout()
    plt.savefig('graphs/03b_time_of_day_recent.png', dpi=150)
    plt.close()
    print("Graph successfully generated and saved to: graphs/03b_time_of_day_recent.png")


def generate_age_ratio(df):
    likes_only = df[df['is_like'] == 1].copy()
    
    age_stats = likes_only.groupby('Age').agg(
        likes_sent=('is_like', 'sum'),
        matches=('is_match', 'sum')
    ).reset_index()
    
    # Filter out ages where you sent less than 3 likes to avoid 1/1 = 100% noise
    age_stats = age_stats[age_stats['likes_sent'] >= 3].copy()
    age_stats['match_ratio'] = age_stats['matches'] / age_stats['likes_sent']
    
    os.makedirs('graphs', exist_ok=True)
    plt.figure(figsize=(12, 6))
    plt.bar(age_stats['Age'], age_stats['match_ratio'], color='#2ecc71')
    plt.title('Match Ratio by Age (Min. 3 Likes Sent)')
    plt.gca().yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    plt.savefig('graphs/04_age_demographics.png')
    plt.close()

def generate_cohort_strategy_ratio(df):
    df = df.copy()
    
    # 1. Determine the Strategy (Short vs Long) for likes sent
    def get_strategy(row):
        # We only care if it was actually a pickup/like
        if row['is_like'] == 0:
            return None
            
        v = str(row['verdict']).upper()
        
        if 'SHORT_PICKUP' in v:
            return 'Short Pickup'
        elif 'LONG_PICKUP' in v:
            return 'Long Pickup'
        return 'Manual/Unknown'

    df['strategy'] = df.apply(get_strategy, axis=1)
    
    # Filter to only known Short/Long likes
    strategy_df = df[df['strategy'].isin(['Short Pickup', 'Long Pickup'])].copy()
    
    # 2. Create Age Cohort Bins
    # Bins: 18-22, 23-25, 26-28, 29-31, 32+
    bins = [0, 22, 25, 28, 31, 100]
    labels = ['18-22', '23-25', '26-28', '29-31', '32+']
    strategy_df['age_cohort'] = pd.cut(strategy_df['Age'], bins=bins, labels=labels, right=True)
    
    # 3. Aggregate data by Cohort and Strategy
    cohort_stats = strategy_df.groupby(['age_cohort', 'strategy'], observed=False).agg(
        likes_sent=('is_like', 'sum'),
        matches=('is_match', 'sum')
    ).reset_index()
    
    # Filter out combinations with too few likes to avoid 100% noise on tiny samples
    min_likes_threshold = 5
    cohort_stats = cohort_stats[cohort_stats['likes_sent'] >= min_likes_threshold].copy()
    
    # Calculate Ratio
    cohort_stats['match_ratio'] = cohort_stats['matches'] / cohort_stats['likes_sent']
    
    # Pivot for easier plotting (Cohorts as rows, Strategies as columns)
    pivot_ratio = cohort_stats.pivot(index='age_cohort', columns='strategy', values='match_ratio').fillna(0)
    pivot_counts = cohort_stats.pivot(index='age_cohort', columns='strategy', values='likes_sent').fillna(0)
    
    # 4. Plotting
    os.makedirs('graphs', exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 7))
    
    # X locations for the groups
    x = np.arange(len(pivot_ratio.index))
    width = 0.35  # Width of the bars
    
    # Safely extract columns if they exist (in case one strategy was never used in the filtered dataset)
    short_ratios = pivot_ratio['Short Pickup'] if 'Short Pickup' in pivot_ratio.columns else np.zeros(len(x))
    long_ratios = pivot_ratio['Long Pickup'] if 'Long Pickup' in pivot_ratio.columns else np.zeros(len(x))
    
    short_counts = pivot_counts['Short Pickup'] if 'Short Pickup' in pivot_counts.columns else np.zeros(len(x))
    long_counts = pivot_counts['Long Pickup'] if 'Long Pickup' in pivot_counts.columns else np.zeros(len(x))
    
    # Plot bars
    rects1 = ax.bar(x - width/2, short_ratios, width, label='Short Pickup', color='#E74C3C')
    rects2 = ax.bar(x + width/2, long_ratios, width, label='Long Pickup', color='#2980B9')
    
    # Formatting
    ax.set_title('Match Ratio by Age Cohort: Short vs. Long Strategy', fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel('Age Cohort', fontsize=12, fontweight='bold')
    ax.set_ylabel('Match Ratio Percentage', fontsize=12, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(pivot_ratio.index, fontsize=11)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
    ax.legend(fontsize=11, frameon=True, shadow=True)
    
    # Add Data Labels (Ratio % and Sample Size n=)
    def add_labels(rects, counts):
        for rect, count in zip(rects, counts):
            height = rect.get_height()
            if height > 0:
                # Ratio text on top
                ax.text(rect.get_x() + rect.get_width()/2., height + 0.005,
                        f'{height*100:.1f}%\n(n={int(count)})',
                        ha='center', va='bottom', fontsize=10, fontweight='bold', color='#333333')

    add_labels(rects1, short_counts)
    add_labels(rects2, long_counts)
    
    # Expand Y limit slightly to make room for the text labels
    max_val = max(short_ratios.max(), long_ratios.max())
    plt.ylim(0, max_val + 0.1)
    
    # Styling
    ax.grid(True, axis='y', color='lightgrey', linestyle='--', linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ['top', 'right']:
        ax.spines[spine].set_visible(False)
        
    plt.tight_layout()
    plt.savefig('graphs/05_strategy_performance.png', dpi=150)
    plt.close()
    
    print("Graph successfully generated and saved to: graphs/05_strategy_performance.png")

if __name__ == "__main__":
    df = database()
    if df is not None:
        generate_daily_ratio_graph(df)
        generate_heatmap(df)
        generate_tod_rolling(df)
        generate_tod_rolling_recent(df)
        generate_age_ratio(df)
        generate_cohort_strategy_ratio(df)
