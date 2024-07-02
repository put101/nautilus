import threading
import queue
import matplotlib.pyplot as plt
import numpy as np
import time

import matplotlib
matplotlib.use('TkAgg')  

# Initialize a thread-safe queue
data_queue = queue.Queue()

# Function simulating data generation in its own thread
def data_generator():
    for i in range(3):
        simulated_data = np.random.random()  # Generate random data
        data_queue.put(simulated_data)  # Put the data into the queue
        time.sleep(0.1)  # Simulate time delay

# Start data generator thread
thread = threading.Thread(target=data_generator)
thread.daemon = True
thread.start()

# Set up the plot for real-time updating
plt.ion()
fig, ax = plt.subplots()
fig.dpi = 70
xdata, ydata = [], []
line, = ax.plot(xdata, ydata, 'r-')

# Make sure the plot stays open for a given duration or until closed by the user
timeout = time.time() + 60*5  # For example, 5 minutes from now
while True:
    # Short pause to allow the GUI to update
    plt.pause(1)
    fig.canvas.flush_events()
    
    
    if time.time() > timeout:
        break  # Exit after the timeout

    try:
        new_data = data_queue.get_nowait()
    except queue.Empty:
        pass  # No new data
    else:
        # Append new data to the plot
        xdata.append(len(xdata))
        ydata.append(new_data)
        line.set_xdata(xdata)
        line.set_ydata(ydata)
        ax.relim()  # Recalculate limits
        ax.autoscale_view(True,True,True)  # Autoscale
        fig.canvas.draw()


#plt.ioff()  # Turn off interactive mode
plt.show()
